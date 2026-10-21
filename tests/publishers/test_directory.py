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
