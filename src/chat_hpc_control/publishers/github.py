"""Fixed-content Git publication with durable intent and non-forced updates."""

from dataclasses import asdict
import hashlib
import fcntl
import os
from pathlib import Path
import re
from ..contracts.codec import decode_json
from ..contracts.errors import ControlError
from ..contracts.results import PublishReceipt
from ..results.collections import result_bytes
from ..results.reader import atomic_pointer
from .base import payload,content_digest


class GitHubPublisher:
    def __init__(self,api,*,repository,branch,state_root,snapshot_store=None,inline_bytes=1048576,artifact_receipt=None):
        if not re.fullmatch('[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._/-]{0,127}',branch):
            raise ControlError('SCHEMA_INVALID','fixed operator repository and branch are required')
        self.api,self.repository,self.branch=api,repository,branch
        self.root=Path(state_root)/hashlib.sha256((repository+':'+branch).encode()).hexdigest()
        self.snapshot_store,self.inline_bytes,self.artifact_receipt=snapshot_store,inline_bytes,artifact_receipt

    def _save(self,collection_id,data):atomic_pointer(self.root/(collection_id+'.json'),data)
    def _load(self,collection_id):return decode_json((self.root/(collection_id+'.json')).read_bytes())
    def _receipt(self,record,state):
        return PublishReceipt(record['collection_id'],'github:'+self.repository+':'+self.branch,state,
            {k:record[k] for k in ('commit','tree','prefix','content_sha256') if k in record})

    def publish(self,collection):
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        fd=os.open(self.root/(collection.collection_id+'.lock'),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ControlError('PUBLISH_UNKNOWN','another writer is publishing this same collection; reconcile it') from exc
            return self._publish(collection)
        finally:os.close(fd)

    def _publish(self,collection):
        data=payload(collection,self.snapshot_store)
        if sum(map(len,data.values()))>self.inline_bytes:
            receipt=self.artifact_receipt
            if receipt is None or receipt.collection_id!=collection.collection_id or receipt.state!='PUBLISHED':
                raise ControlError('CAPABILITY_UNSUPPORTED','stage and verify an Artifact before publishing large raw evidence')
            data=payload(collection,include_raw=False)
            data['artifact-receipt.json']=result_bytes(asdict(receipt))
        path=self.root/(collection.collection_id+'.json')
        if path.exists():return self.reconcile_publish(self._receipt(self._load(collection.collection_id),'PUBLISH_UNKNOWN'))
        record={'collection_id':collection.collection_id,'prefix':'results/'+collection.collection_id,
                'content_sha256':content_digest(data),'phase':'RESERVED'}
        self._save(collection.collection_id,record)
        try:
            base=self.api.get_ref(self.branch)
            full={record['prefix']+'/'+name:raw for name,raw in data.items()}
            tree=self.api.create_tree(base,full)
            record.update(base=base,tree=tree,phase='TREE_CREATED');self._save(collection.collection_id,record)
            commit=self.api.create_commit(base,tree,'chat-hpc-control collection '+collection.collection_id)
            record.update(commit=commit,phase='COMMIT_CREATED');self._save(collection.collection_id,record)
            self.api.update_ref(self.branch,commit,force=False)
        except Exception:
            return self._receipt(record,'PUBLISH_UNKNOWN')
        return self.reconcile_publish(self._receipt(record,'PUBLISH_UNKNOWN'))

    def reconcile_publish(self,receipt):
        try:
            if receipt.target != "github:"+self.repository+":"+self.branch:raise ValueError("publication target mismatch")
            record=self._load(receipt.collection_id);head=self.api.get_ref(self.branch)
            commit=record.get('commit',head)
            found=self.api.read_files(commit,record['prefix'])
            if content_digest(found)!=record['content_sha256'] or not self.api.is_ancestor(commit,head):
                return self._receipt(record,'PUBLISH_UNKNOWN')
            record.update(commit=commit,phase='PUBLISHED');self._save(receipt.collection_id,record)
            return self._receipt(record,'PUBLISHED')
        except Exception:return PublishReceipt(receipt.collection_id,receipt.target,'PUBLISH_UNKNOWN',receipt.identity)
