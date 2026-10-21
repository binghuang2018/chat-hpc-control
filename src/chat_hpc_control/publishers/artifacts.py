"""Two-phase Actions upload: deterministic local tar, verified runtime receipt."""

from dataclasses import asdict
from datetime import datetime,timezone
import gzip
import hashlib
import io
from pathlib import Path
import tarfile
from ..contracts.errors import ControlError
from ..contracts.results import PublishReceipt
from ..results.collections import result_bytes
from ..worker.receipt import write_once,digest_file
from .base import payload


class ArtifactBackend:
    def __init__(self,stage_root,*,snapshot_store=None,actions_context=None,get_artifact=None):
        self.root=Path(stage_root);self.snapshot_store=snapshot_store
        self.context,self.get_artifact=actions_context,get_artifact
        if not self.root.is_absolute() or self.root.is_symlink():raise ControlError('SCHEMA_INVALID','explicit Artifact staging root required')

    def stage(self,collection):
        data=payload(collection,self.snapshot_store);stream=io.BytesIO()
        with gzip.GzipFile(fileobj=stream,mode='wb',filename='',mtime=0) as gz:
            with tarfile.open(fileobj=gz,mode='w') as archive:
                for name,raw in sorted(data.items()):
                    item=tarfile.TarInfo(name);item.size=len(raw);item.mode=0o400
                    archive.addfile(item,io.BytesIO(raw))
        raw=stream.getvalue();digest=hashlib.sha256(raw).hexdigest()
        path=self.root/'archives'/(digest+'.tar.gz');write_once(path,raw)
        context=self.context or {}
        name='chc-'+collection.collection_id+'-'+str(context.get('run_id','offline'))+'-'+str(context.get('run_attempt',1))
        staged={'collection_id':collection.collection_id,'archive_sha256':digest,'path':str(path),'artifact_name':name}
        write_once(self.root/'staged'/(name+'.json'),result_bytes(staged))
        return staged

    def record_upload(self,staged,upload_result,*,previous=None):
        context=self.context
        if not context or context.get('github_actions') is not True or not self.get_artifact:
            raise ControlError('AUTH_DENIED','only a trusted Actions runtime with API readback can attest an upload')
        path=Path(staged['path'])
        if (path.parent!=self.root/'archives' or path.is_symlink() or digest_file(path)!=staged['archive_sha256']
                or upload_result.get('archive_sha256')!=staged['archive_sha256']):
            raise ControlError('RESULT_UNVERIFIED','staged archive changed before upload attestation')
        aid=upload_result.get('artifact_id')
        if type(aid)!=int or aid<=0:raise ControlError('SCHEMA_INVALID','Artifact ID must be a positive integer')
        digest=upload_result.get('artifact_digest','')
        expected_url=f"https://github.com/{context['repository']}/actions/runs/{context['run_id']}/artifacts/{aid}"
        if (len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest)
                or upload_result.get('artifact_url')!=expected_url):
            raise ControlError('SCHEMA_INVALID','upload output identity is malformed')
        identity={'artifact_id':aid,'artifact_name':staged['artifact_name'],'artifact_digest':digest,
                  'archive_sha256':staged['archive_sha256'],'repository':context['repository'],
                  'run_id':context['run_id'],'url':expected_url,'availability':'UNVERIFIED',
                  'content_binding':'trusted-workflow-upload'}
        write_once(self.root/'upload-intents'/staged['collection_id']/(str(aid)+'.json'),
                   result_bytes({'staged':staged,'upload_result':upload_result,'context':context}))
        try:meta=self.get_artifact(aid)
        except Exception:
            return PublishReceipt(staged['collection_id'],'github-artifact:'+context['repository'],'PUBLISH_UNKNOWN',identity)
        if (meta['id']!=aid or meta['name']!=staged['artifact_name'] or meta['workflow_run']['id']!=context['run_id']
                or meta.get('digest')!='sha256:'+digest or meta.get('expired') is not False
                or datetime.fromisoformat(meta['expires_at'].replace('Z','+00:00'))<=datetime.now(timezone.utc)):
            raise ControlError('RESULT_UNVERIFIED','Artifact API identity, digest or retention differs from runtime output')
        identity.update(expires_at=meta['expires_at'],availability='AVAILABLE')
        if previous:
            if (previous.collection_id!=staged['collection_id'] or previous.identity['artifact_id']==aid
                    or previous.identity['archive_sha256']!=staged['archive_sha256']
                    or previous.target!='github-artifact:'+context['repository']):
                raise ControlError('SCHEMA_INVALID','renewal requires a new upload ID for the same collection')
            identity['renewed_from']=previous.identity['artifact_id']
        receipt=PublishReceipt(staged['collection_id'],'github-artifact:'+context['repository'],'PUBLISHED',identity)
        raw=result_bytes(asdict(receipt));write_once(self.root/'receipts'/receipt.collection_id/(hashlib.sha256(raw).hexdigest()+'.json'),raw)
        return receipt

    def reconcile_publish(self,receipt):
        try:
            if not self.get_artifact:raise ValueError('API unavailable')
            meta=self.get_artifact(receipt.identity['artifact_id'])
            if (meta['id']!=receipt.identity['artifact_id'] or meta['digest']!='sha256:'+receipt.identity['artifact_digest']
                    or meta['name']!=receipt.identity['artifact_name'] or meta['workflow_run']['id']!=receipt.identity['run_id']):raise ValueError('Artifact changed')
            expired=meta.get('expired') or datetime.fromisoformat(meta['expires_at'].replace('Z','+00:00'))<=datetime.now(timezone.utc)
            return PublishReceipt(receipt.collection_id,receipt.target,'PUBLISHED',
                                  {**receipt.identity,'availability':'EXPIRED' if expired else 'AVAILABLE','expires_at':meta['expires_at']})
        except Exception:return PublishReceipt(receipt.collection_id,receipt.target,'PUBLISH_UNKNOWN',receipt.identity)

    def renew(self,receipt):
        return PublishReceipt(receipt.collection_id,receipt.target,'RENEWAL_REQUIRED',
            {**receipt.identity,'action':'stage in a new trusted workflow run, upload, then record_upload(previous=old_receipt)'})
