"""Authorized pinned reads; neither reads nor pagination submit or collect."""

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import tempfile
from ..contracts.codec import decode_json
from ..contracts.errors import ControlError
from ..contracts.results import CollectionRef,ResultPage
from ..core.auth import authorize,authorize_run
from ..worker.receipt import write_once
from .collections import read_collection,result_bytes


def atomic_pointer(path,data):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.pointer-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(result_bytes(data));stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
        directory=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:Path(name).unlink(missing_ok=True)


class CollectionReader:
    def __init__(self,store,site):
        self.store,self.site=store,site
        path=site.root/'cursor.key'
        if not path.exists():write_once(path,os.urandom(32))
        if path.is_symlink() or path.stat().st_mode & 0o077:raise ControlError('AUTH_DENIED','cursor key permissions are not private')
        self.key=path.read_bytes()
        if len(self.key)!=32:raise ControlError('AUTH_DENIED','invalid private cursor key')

    def _row(self,run_id,context):
        authorize(context,'results:read',None)
        row=self.store.get_run(run_id)
        authorize_run(context,row['owner'],row['site_id'],'results:read')
        return row

    def index(self,ref):
        if not ref.root.resolve().is_relative_to(self.site.root.resolve()):
            raise ControlError('RESULT_UNVERIFIED','collection outside site root')
        read_collection(ref)
        data={'run_id':ref.run_id,'collection_id':ref.collection_id,'root':str(ref.root.relative_to(self.site.root))}
        write_once(self.site.root/'collection-index'/ref.run_id/(ref.collection_id+'.json'),result_bytes(data))
        atomic_pointer(self.site.root/'runs'/ref.run_id/'latest-collection.json',data)

    def _ref(self,run_id,collection_id):
        if collection_id is None:path=self.site.root/'runs'/run_id/'latest-collection.json'
        else:
            if not re.fullmatch('[0-9a-f]{64}',collection_id):raise ValueError('invalid collection id')
            path=self.site.root/'collection-index'/run_id/(collection_id+'.json')
        if not path.exists():return None
        data=decode_json(path.read_bytes());root=self.site.root/data['root']
        if data['run_id']!=run_id or not root.resolve().is_relative_to(self.site.root.resolve()) or root.is_symlink():
            raise ValueError('collection pointer changed')
        if collection_id is not None and collection_id!=data['collection_id']:raise ValueError('pointer mismatch')
        return CollectionRef(run_id,data['collection_id'],root)

    def _encode(self,data):
        raw=result_bytes(data);signature=hmac.digest(self.key,raw,'sha256')
        return base64.urlsafe_b64encode(signature+raw).decode().rstrip('=')

    def _decode(self,cursor):
        if not isinstance(cursor,str) or len(cursor)>4096:raise ValueError('invalid cursor')
        data=base64.b64decode(cursor+'='*(-len(cursor)%4),altchars=b'-_',validate=True)
        if not hmac.compare_digest(data[:32],hmac.digest(self.key,data[32:],'sha256')):raise ValueError('cursor signature')
        return decode_json(data[32:])

    def get_page(self,run_id,collection_id,fields,cursor,page_size,context):
        row=self._row(run_id,context)
        try:
            offset=0
            if cursor:
                pin=self._decode(cursor)
                if (pin['run_id']!=run_id or pin['fields']!=fields or type(pin['offset'])!=int or pin['offset']<0
                        or collection_id is not None and collection_id!=pin['collection_id']):raise ValueError('cursor binding')
                collection_id=pin['collection_id'];offset=pin['offset']
            if type(page_size)!=int or not 1<=page_size<=100:raise ValueError('page size')
            ref=self._ref(run_id,collection_id)
            if ref is None:
                if collection_id or cursor:raise ValueError('collection unavailable')
                return ResultPage(None,[],None,{'collection_state':'PENDING','execution_state':row['execution_state'],
                    'integrity':'UNVERIFIED','completeness':'UNVERIFIED','scientific_acceptance':'NOT_EVALUATED','data_ready':False})
            documents=read_collection(ref);records=documents['records.json']['records']
            selected=records[offset:offset+page_size]
            if fields:
                def project(record):
                    aliases={'geometry':record.get('coordinates'),'units':{'energy':record.get('energy_unit'),'gradient':record.get('gradient_unit')},
                             'provenance':record.get('raw_sources')}
                    return {key:record[key] if key in record else aliases[key] for key in fields if key in record or key in aliases}
                selected=[project(record) for record in selected]
            next_cursor=None
            if offset+page_size<len(records):next_cursor=self._encode({'run_id':run_id,'collection_id':ref.collection_id,'fields':fields,'offset':offset+page_size})
            return ResultPage(ref.collection_id,selected,next_cursor,documents['summary.json'])
        except (OSError,ValueError,KeyError,TypeError) as exc:
            raise ControlError('RESULT_UNVERIFIED','pinned collection or cursor could not be verified') from exc

    def get_manifest(self,run_id,collection_id,context):
        self._row(run_id,context)
        try:
            ref=self._ref(run_id,collection_id)
            if ref is None:
                if collection_id:raise ValueError('collection absent')
                return {'run_id':run_id,'collection_id':None,'collection_state':'PENDING','files':[]}
            documents=read_collection(ref)
            publications=[]
            for path in sorted((self.site.root/'publications'/ref.collection_id).glob('*.json')):
                raw=path.read_bytes()
                if path.is_symlink() or hashlib.sha256(raw).hexdigest()!=path.stem:raise ValueError('publication receipt changed')
                receipt=decode_json(raw)
                if receipt['collection_id']!=ref.collection_id:raise ValueError('publication belongs to another collection')
                publications.append(receipt)
            return {'run_id':run_id,'collection_id':ref.collection_id,'collection_state':'COLLECTED',
                    'files':documents['raw-manifest.json']['files'],'availability':'LOCAL_ONLY',
                    'summary':documents['summary.json'],'publication_receipts':publications}
        except (OSError,ValueError,KeyError,TypeError) as exc:
            raise ControlError('RESULT_UNVERIFIED','collection manifest could not be verified') from exc
