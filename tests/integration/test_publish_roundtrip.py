from tests.publishers.conftest import publish_case
from tests.publishers.test_github import FakeGitHub
import pytest


def test_raw_export_fixed_numerical_commit_roundtrip(publish_case):
    try:
        from chat_hpc_control.publishers.artifacts import ArtifactBackend
        from chat_hpc_control.publishers.github import GitHubPublisher
    except ModuleNotFoundError:pytest.fail('publication roundtrip missing')
    ref,snapshots,root=publish_case
    staged=ArtifactBackend(root/'stage',snapshot_store=snapshots).stage(ref)
    assert staged['archive_sha256'] and staged['path'].endswith('.tar.gz')
    remote=FakeGitHub()
    receipt=GitHubPublisher(remote,repository='example/results',branch='results',state_root=root/'state',snapshot_store=snapshots).publish(ref)
    files=remote.read_files(receipt.identity['commit'],receipt.identity['prefix'])
    assert 'collection/records.json' in files and 'raw/stdout.log' in files
    assert b'NOT_EVALUATED' in files['collection/summary.json']
