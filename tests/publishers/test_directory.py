import importlib
import pytest


def api():
    try:return importlib.import_module('chat_hpc_control.publishers.directory')
    except ModuleNotFoundError:pytest.fail('directory publisher missing')


def test_idempotent_verified_directory_publish(publish_case):
    ref,snapshots,root=publish_case
    publisher=api().DirectoryPublisher(root/'export',snapshot_store=snapshots)
    one=publisher.publish(ref)
    assert one.state=='PUBLISHED'
    files={str(p.relative_to(root/'export')):p.read_bytes() for p in (root/'export').rglob('*') if p.is_file()}
    two=publisher.publish(ref)
    assert one==two and publisher.reconcile_publish(one).state=='PUBLISHED'
    assert files=={str(p.relative_to(root/'export')):p.read_bytes() for p in (root/'export').rglob('*') if p.is_file()}
    assert (root/'export'/ref.collection_id/'raw/stdout.log').read_bytes()==b'synthetic output\n'


def test_tampered_collection_or_raw_is_not_published(publish_case):
    ref,snapshots,root=publish_case
    publisher=api().DirectoryPublisher(root/'export',snapshot_store=snapshots)
    (ref.root/'summary.json').chmod(0o600);(ref.root/'summary.json').write_text('{}')
    with pytest.raises(Exception):publisher.publish(ref)
    assert not (root/'export'/ref.collection_id).exists()


def test_export_does_not_follow_existing_output_link(publish_case):
    ref,snapshots,root=publish_case
    outside=root/'outside';outside.mkdir()
    target=root/'export'/ref.collection_id;target.mkdir(parents=True)
    (target/'raw').symlink_to(outside,target_is_directory=True)
    with pytest.raises(Exception):api().DirectoryPublisher(root/'export',snapshot_store=snapshots).publish(ref)
    assert not list(outside.iterdir())


def test_raw_snapshot_tamper_is_rejected(publish_case):
    ref,snapshots,root=publish_case
    raw=next(snapshots.glob('*/stdout.log'));raw.write_bytes(b'tampered')
    with pytest.raises(Exception):api().DirectoryPublisher(root/'export',snapshot_store=snapshots).publish(ref)


def test_raw_export_uses_inventory_budget_not_numerical_parser_limit(tmp_path):
    import hashlib
    from chat_hpc_control.contracts.results import OutputSnapshot,ParseReport
    from chat_hpc_control.results.collections import create_collection,result_bytes
    from chat_hpc_control.publishers.base import payload
    size=64*1024*1024+1
    stage=tmp_path/'stage';stage.mkdir()
    large=stage/'large.out'
    with large.open('wb') as stream:stream.truncate(size)
    with large.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    manifest=b'{"task":{"expected_results":null}}'
    (stage/'task-manifest.json').write_bytes(manifest)
    files=[{'path':'large.out','size':size,'sha256':digest},{'path':'task-manifest.json','size':len(manifest),'sha256':hashlib.sha256(manifest).hexdigest()}]
    terminal={'execution_state':'COMPLETED','integrity':'VERIFIED'}
    identity={'files':files,'terminal':terminal,'manifest_sha256':'a'*64}
    sha=hashlib.sha256(result_bytes(identity)).hexdigest();store=tmp_path/'snapshots';store.mkdir();root=store/sha;stage.rename(root)
    snapshot=OutputSnapshot(root,files,'a'*64,terminal)
    ref=create_collection('synthetic-large',snapshot,ParseReport('raw-only',{'version':'1'},supported=False))
    exported=payload(ref,store)
    assert len(exported['raw/large.out'])==size
