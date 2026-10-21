"""Private durable human request/intent ledger, independent of provider IDs."""

import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import uuid
from ..contracts.codec import parse_task
from ..contracts.errors import ControlError
from ..core.manifest import canonical_bytes

APP_ID=0x4348434C


class ClientSessionStore:
    def __init__(self,path,db):self.path,self.db,self._mutex=path,db,threading.RLock()

    @classmethod
    def open(cls,path):
        path=Path(path);path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        if path.is_symlink() or path.exists() and path.stat().st_mode & 0o077:
            raise ControlError('AUTH_DENIED','client session file must be private')
        existed=path.exists() and path.stat().st_size>0
        fd=os.open(path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600);os.close(fd)
        db=sqlite3.connect(path,check_same_thread=False,isolation_level=None,timeout=10);db.row_factory=sqlite3.Row
        if existed and (db.execute('PRAGMA application_id').fetchone()[0]!=APP_ID or db.execute('PRAGMA user_version').fetchone()[0]!=1):
            db.close();raise ControlError('SCHEMA_INVALID','not a supported client session database')
        if not existed:
            db.executescript(f'''PRAGMA application_id={APP_ID}; PRAGMA user_version=1;
            CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE requests(id TEXT PRIMARY KEY,prompt TEXT NOT NULL,rerun_of TEXT,manifest TEXT,intent_key TEXT,
                run_id TEXT,attempted INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE validations(request_id TEXT,digest TEXT,task TEXT,PRIMARY KEY(request_id,digest));
            CREATE TABLE conversations(request_id TEXT,provider TEXT,history TEXT,previous_id TEXT,pending TEXT,
                PRIMARY KEY(request_id,provider));
            CREATE TABLE calls(request_id TEXT,provider TEXT,call_id TEXT,fingerprint TEXT,response TEXT,
                PRIMARY KEY(request_id,provider,call_id));''')
        db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA synchronous=FULL')
        return cls(path,db)

    def close(self):self.db.close()

    def _meta(self,key):
        row=self.db.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else None

    def bind_identity(self,site_id,principal):
        with self._mutex:
            value={'site_id':site_id,'principal':principal};old=self._meta('identity')
            if old is not None and old!=value:raise ControlError('AUTH_DENIED','session belongs to another authenticated identity')
            self.db.execute('INSERT OR IGNORE INTO meta VALUES(?,?)',('identity',json.dumps(value)))

    def begin_request(self,client_request_id,prompt,*,rerun_of=None):
        if (not isinstance(client_request_id,str) or not re.fullmatch('[A-Za-z0-9._:-]{1,128}',client_request_id)
                or not isinstance(prompt,str) or not 0<len(prompt.encode())<=65536):
            raise ControlError('SCHEMA_INVALID','explicit client request ID and bounded prompt are required')
        with self._mutex:
            if self._meta('identity') is None:raise ControlError('AUTH_DENIED','bind the authenticated client identity first')
            old=self.db.execute('SELECT * FROM requests WHERE id=?',(client_request_id,)).fetchone()
            if old and (old['prompt']!=prompt or old['rerun_of']!=rerun_of):
                raise ControlError('IDEMPOTENCY_CONFLICT','human request ID already freezes another intent')
            self.db.execute('INSERT OR IGNORE INTO requests(id,prompt,rerun_of) VALUES(?,?,?)',(client_request_id,prompt,rerun_of))
            self.db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',('active',json.dumps(client_request_id)))

    def current(self,prompt=None):
        with self._mutex:
            request_id=self._meta('active')
            row=self.db.execute('SELECT * FROM requests WHERE id=?',(request_id,)).fetchone()
            if row is None or prompt is not None and row['prompt']!=prompt:
                raise ControlError('IDEMPOTENCY_CONFLICT','begin an explicit human request before running a turn')
            return {**dict(row),**self._meta('identity')}

    def reserve_intent(self,client_request_id,operation_slot,manifest_sha256):
        if operation_slot!='primary' or not re.fullmatch('[0-9a-f]{64}',manifest_sha256):
            raise ControlError('SCHEMA_INVALID','only the explicitly permitted submission slot may reserve an intent')
        with self._mutex:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                row=self.db.execute('SELECT * FROM requests WHERE id=?',(client_request_id,)).fetchone()
                if row is None:raise ControlError('AUTH_DENIED','unknown human request')
                if row['intent_key']:
                    if row['manifest']!=manifest_sha256:raise ControlError('IDEMPOTENCY_CONFLICT','one human intent cannot change frozen manifest')
                    key=row['intent_key']
                else:
                    earlier=self.db.execute('SELECT * FROM requests WHERE manifest=? AND id<>? ORDER BY rowid DESC',
                                            (manifest_sha256,client_request_id)).fetchall()
                    if earlier and (not row['rerun_of'] or row['rerun_of'] not in {r['run_id'] for r in earlier if r['run_id']}):
                        raise ControlError('IDEMPOTENCY_CONFLICT','existing calculation intent requires reuse or an explicit run-bound rerun')
                    key='client:'+str(uuid.uuid4())
                    self.db.execute('UPDATE requests SET manifest=?,intent_key=? WHERE id=?',(manifest_sha256,key,client_request_id))
                self.db.execute('COMMIT');return key
            except Exception:self.db.execute('ROLLBACK');raise

    def pin_validation(self,request_id,data):
        if data.get('valid') is not True or not re.fullmatch('[0-9a-f]{64}',data.get('manifest_sha256','')):
            raise ControlError('SCHEMA_INVALID','validation did not provide an immutable task identity')
        task=parse_task(json.dumps(data['task']).encode())
        with self._mutex:self.db.execute('INSERT OR REPLACE INTO validations VALUES(?,?,?)',
            (request_id,data['manifest_sha256'],canonical_bytes(task.to_dict()).decode()))

    def approved_task(self,request_id,digest):
        row=self.db.execute('SELECT task FROM validations WHERE request_id=? AND digest=?',(request_id,digest)).fetchone()
        if row is None:raise ControlError('INPUT_CHANGED','submit must reference a saved successful validation')
        return json.loads(row[0])

    def mark_attempted(self,request_id):
        with self._mutex:self.db.execute('UPDATE requests SET attempted=1 WHERE id=?',(request_id,))

    def record_run(self,request_id,run_id):
        if not isinstance(run_id,str) or not run_id:raise ControlError('SCHEMA_INVALID','missing run identity')
        with self._mutex:
            row=self.db.execute('SELECT run_id FROM requests WHERE id=?',(request_id,)).fetchone()
            if row is None or row[0] and row[0]!=run_id:raise ControlError('IDEMPOTENCY_CONFLICT','intent returned a different run')
            self.db.execute('UPDATE requests SET run_id=? WHERE id=?',(run_id,request_id))

    def conversation(self,request_id,provider,initial):
        row=self.db.execute('SELECT * FROM conversations WHERE request_id=? AND provider=?',(request_id,provider)).fetchone()
        return {'history':json.loads(row['history']),'previous_id':row['previous_id'],
                'pending':json.loads(row['pending']) if row['pending'] else None} if row else {
                    'history':initial,'previous_id':None,'pending':None}

    def save_conversation(self,request_id,provider,history,previous_id,pending=None):
        with self._mutex:self.db.execute('INSERT OR REPLACE INTO conversations VALUES(?,?,?,?,?)',
            (request_id,provider,json.dumps(history,allow_nan=False),previous_id,json.dumps(pending,allow_nan=False) if pending else None))

    def saved_call(self,request_id,provider,call):
        fingerprint=hashlib.sha256(canonical_bytes({'name':call.name,'arguments':call.arguments})).hexdigest()
        with self._mutex:
            row=self.db.execute('SELECT * FROM calls WHERE request_id=? AND provider=? AND call_id=?',
                                (request_id,provider,call.provider_call_id)).fetchone()
            if row and row['fingerprint']!=fingerprint:raise ControlError('IDEMPOTENCY_CONFLICT','provider reused a call ID for different arguments')
            return fingerprint,json.loads(row['response']) if row else None

    def save_call(self,request_id,provider,call,fingerprint,response):
        with self._mutex:self.db.execute('INSERT OR IGNORE INTO calls VALUES(?,?,?,?,?)',
            (request_id,provider,call.provider_call_id,fingerprint,json.dumps(response.to_dict(),allow_nan=False)))
