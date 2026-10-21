"""Explicit operator/Actions publication entry point, separate from chat tools."""

from dataclasses import asdict
import json
import hashlib
from datetime import datetime, timezone
import os
from pathlib import Path
from ..contracts.auth import PeerIdentity
from ..contracts.codec import decode_json
from ..contracts.errors import ControlError
from ..contracts.results import CollectionRef
from ..contracts.tools import ToolCall
from ..core.auth import authorize,context_from_peer
from ..core.rpc import rpc_call
from ..results.collections import read_collection,result_bytes
from .base import record_publication
from .directory import DirectoryPublisher
from .github import GitHubPublisher
from .github_api import GitHubWriteApi
from .artifacts import ArtifactBackend


def _actions_context(repository):
    if os.environ.get('GITHUB_ACTIONS')!='true':return None
    if os.environ.get('GITHUB_REPOSITORY')!=repository:raise ControlError('AUTH_DENIED','Actions runtime repository differs from publication target')
    return {'github_actions':True,'repository':repository,'run_id':int(os.environ['GITHUB_RUN_ID']),
            'run_attempt':int(os.environ['GITHUB_RUN_ATTEMPT'])}


def operate(site,*,operation,target,collection_root,upload_result=None,previous=None):
    context=context_from_peer(PeerIdentity(os.getuid(),os.getgid(),os.getpid()),{},site)
    authorize(context,'results:publish',None)
    config=site.settings.get('publish_targets',{}).get(target)
    if not config:raise ControlError('AUTH_DENIED','publication target is not operator allowlisted')
    root=Path(collection_root)
    if root.is_symlink() or not root.resolve().is_relative_to(site.root.resolve()):
        raise ControlError('RESULT_UNVERIFIED','collection must belong to the configured private site root')
    manifest=decode_json((root/'collection.json').read_bytes())
    ref=CollectionRef(manifest['run_id'],root.name,root);read_collection(ref)
    # Read authorization remains tied to the actual broker owner and pinned ID.
    checked=rpc_call(site.root/'broker.sock',ToolCall('get_result_manifest',{
        'site_id':site.site_id,'run_id':ref.run_id,'collection_id':ref.collection_id}))
    if not checked.ok or checked.data.get('collection_id')!=ref.collection_id:
        raise ControlError('AUTH_DENIED','broker did not authorize this pinned collection')
    snapshot_store=Path(config.get('snapshot_store',site.root/'snapshots'))
    api=None
    try:
        if config['kind']=='directory':
            if operation!='publish':raise ControlError('SCHEMA_INVALID','directory target only supports publish')
            result=DirectoryPublisher(Path(config['path']),snapshot_store=snapshot_store).publish(ref)
        elif config['kind'] in {'github','artifact'}:
            repository=config['repository']
            if operation in {'publish','record-upload'}:
                api=GitHubWriteApi(repository,os.environ.get(config['token_env'],''))
            if config['kind']=='github':
                if operation!='publish':raise ControlError('SCHEMA_INVALID','GitHub target only supports publish')
                artifact=None
                if config.get('artifact_receipts_dir'):
                    from ..contracts.results import PublishReceipt
                    candidates=[]
                    for receipt_path in (Path(config['artifact_receipts_dir'])/ref.collection_id).glob('*.json'):
                        raw=receipt_path.read_bytes()
                        if receipt_path.is_symlink() or hashlib.sha256(raw).hexdigest()!=receipt_path.stem:
                            raise ControlError('RESULT_UNVERIFIED','Artifact receipt inventory changed')
                        candidate=PublishReceipt(**decode_json(raw))
                        if (candidate.collection_id==ref.collection_id and candidate.state=='PUBLISHED'
                                and candidate.target=='github-artifact:'+repository
                                and candidate.identity.get('availability')=='AVAILABLE'
                                and datetime.fromisoformat(candidate.identity['expires_at'].replace('Z','+00:00'))>datetime.now(timezone.utc)):
                            candidates.append(candidate)
                    if candidates:artifact=max(candidates,key=lambda r:r.identity['expires_at'])
                if config.get('artifact_receipt'):
                    from ..contracts.results import PublishReceipt
                    artifact=PublishReceipt(**decode_json(Path(config['artifact_receipt']).read_bytes()))
                result=GitHubPublisher(api,repository=repository,branch=config['branch'],
                    state_root=Path(config['state_root']),snapshot_store=snapshot_store,
                    inline_bytes=config.get('inline_bytes',1048576),artifact_receipt=artifact).publish(ref)
            else:
                backend=ArtifactBackend(Path(config['stage_root']),snapshot_store=snapshot_store,
                    actions_context=_actions_context(repository),
                    get_artifact=(lambda aid:api.get('/repos/'+repository+'/actions/artifacts/'+str(aid))) if api else None)
                staged=backend.stage(ref)
                if operation=='stage':
                    staged_file=backend.root/'staged'/(staged['artifact_name']+'.json')
                    result={**staged,'staged_file':str(staged_file)}
                    output=os.environ.get('GITHUB_OUTPUT')
                    if output:
                        with Path(output).open('a') as stream:
                            for key,value in {'archive_path':staged['path'],'artifact_name':staged['artifact_name'],
                                              'staged_file':str(staged_file),'archive_sha256':staged['archive_sha256']}.items():
                                if '\n' in value or '\r' in value:raise ControlError('SCHEMA_INVALID','workflow output contains line break')
                                stream.write(key+'='+value+'\n')
                    return result
                if operation!='record-upload' or upload_result is None:raise ControlError('SCHEMA_INVALID','stage or record-upload required')
                result=backend.record_upload(staged,upload_result,previous=previous)
        else:raise ControlError('CAPABILITY_UNSUPPORTED','publication backend is not installed')
        record_publication(site,result)
        return asdict(result)
    finally:
        if api:api.close()
