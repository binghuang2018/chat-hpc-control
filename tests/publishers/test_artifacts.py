import importlib,hashlib
from datetime import datetime,timedelta,timezone
import pytest


def api():
    try:return importlib.import_module('chat_hpc_control.publishers.artifacts')
    except ModuleNotFoundError:pytest.fail('artifact backend missing')


def context(run=123):return {'github_actions':True,'repository':'example/results','run_id':run,'run_attempt':1}


def test_not_in_actions_cannot_claim_upload(publish_case):
    ref,snapshots,root=publish_case
    backend=api().ArtifactBackend(root/'stage',snapshot_store=snapshots)
    staged=backend.stage(ref)
    with pytest.raises(Exception):backend.record_upload(staged,{'artifact_id':1})


def test_expiry_and_renewal_preserve_collection(publish_case):
    ref,snapshots,root=publish_case;meta={}
    backend=api().ArtifactBackend(root/'stage',snapshot_store=snapshots,actions_context=context(),get_artifact=lambda aid:meta[aid])
    staged=backend.stage(ref)
    original={p.name:p.read_bytes() for p in ref.root.iterdir() if p.is_file()}
    def upload(aid,run,stage):
        meta[aid]={'id':aid,'name':stage['artifact_name'],'expired':False,
          'expires_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),
          'digest':'sha256:'+'b'*64,'workflow_run':{'id':run}}
        return {'artifact_id':aid,'artifact_digest':'b'*64,'archive_sha256':stage['archive_sha256'],
          'artifact_url':f'https://github.com/example/results/actions/runs/{run}/artifacts/{aid}'}
    one=backend.record_upload(staged,upload(1,123,staged))
    assert one.state=='PUBLISHED'
    meta[1]['expired']=True
    expired=backend.reconcile_publish(one)
    assert expired.identity['availability']=='EXPIRED'
    assert backend.renew(expired).state=='RENEWAL_REQUIRED'
    newer=api().ArtifactBackend(root/'stage',snapshot_store=snapshots,actions_context=context(124),get_artifact=lambda aid:meta[aid])
    staged2=newer.stage(ref)
    two=newer.record_upload(staged2,upload(2,124,staged2),previous=one)
    assert two.identity['artifact_id']==2 and two.identity['renewed_from']==1
    assert original=={p.name:p.read_bytes() for p in ref.root.iterdir() if p.is_file()}
    assert len(list((root/'stage'/'receipts'/ref.collection_id).glob('*.json')))==2


def test_unknown_upload_readback_retains_identity_for_recovery(publish_case):
    ref,snapshots,root=publish_case;available=False;meta={}
    def get(aid):
        if not available:raise ConnectionError('synthetic API timeout after upload')
        return meta
    backend=api().ArtifactBackend(root/'stage',snapshot_store=snapshots,actions_context=context(),get_artifact=get)
    staged=backend.stage(ref)
    upload={'artifact_id':7,'artifact_digest':'b'*64,'archive_sha256':staged['archive_sha256'],
            'artifact_url':'https://github.com/example/results/actions/runs/123/artifacts/7'}
    receipt=backend.record_upload(staged,upload)
    assert receipt.state=='PUBLISH_UNKNOWN' and receipt.identity['artifact_id']==7
    available=True
    meta.update(id=7,name=staged['artifact_name'],digest='sha256:'+'b'*64,workflow_run={'id':123},expired=False,
                expires_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
    assert backend.reconcile_publish(receipt).state=='PUBLISHED'
