from copy import deepcopy
import base64,hashlib,importlib,json
from pathlib import Path
import pytest
from chat_hpc_control.contracts.results import CompatibilityReport
from tests.transports.test_github import github_case


def api():
    try:return importlib.import_module('chat_hpc_control.compat.legacy')
    except ModuleNotFoundError:pytest.fail('read-only legacy inspector missing')


def old_digest(raw):
    return hashlib.sha256((json.dumps(json.loads(raw),ensure_ascii=True,sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest()


def make_snapshot(root):
    root.mkdir();raw=(Path(__file__).parents[1]/'fixtures/legacy/manifest.json').read_bytes()
    (root/'manifest.json').write_bytes(raw)
    (root/'input.inp').write_bytes(b'***,synthetic\n')
    (root/'state.json').write_text('{"job_id":"0","state":"RUNNING"}')
    index={'schema':'hpc-control/offline-export/v1','offline':True,'records':[{
      'task_id':'synthetic-old-h2','kind':'molpro','manifest_file':'manifest.json',
      'digest_algorithm':'hpc-control-qc-json-v1','claimed_digest':old_digest(raw),
      'legacy_state':'RUNNING','legacy_job_id':'0'}]}
    (root/'legacy-index.json').write_text(json.dumps(index))
    return root,index


def test_legacy_bytes_digest_and_running_state_are_not_rekeyed(tmp_path):
    module=api();root,index=make_snapshot(tmp_path/'offline')
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
    for p in root.iterdir():p.chmod(0o400)
    root.chmod(0o500)
    try:
        report=module.inspect_legacy(root)
        assert not report.issues,report
        record=report.records[0]
        assert record['envelope']['legacy_digest']['value']==index['records'][0]['claimed_digest']
        assert record['adoptable'] is False and record['legacy_state']=='RUNNING'
        assert record['native_identity']=='UNVERIFIED'
        assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
    finally:root.chmod(0o700)


def test_original_unicode_json_bytes_are_retained():
    raw=b'{ "version":1,"task_id":"synthetic","name":"\\u6c34" }\n'
    envelope=api().wrap_legacy(raw,'hpc-control-qc-json-v1',old_digest(raw))
    assert envelope['legacy_digest']['value']==old_digest(raw)
    assert base64.b64decode(envelope['raw_base64'])==raw
    assert envelope['storage_sha256']==hashlib.sha256(raw).hexdigest()
    assert envelope['digest_verified']


def test_corrupt_or_unknown_digest_stays_unverified(tmp_path):
    module=api();root,index=make_snapshot(tmp_path/'offline')
    (root/'manifest.json').write_text('{}')
    report=module.inspect_legacy(root)
    assert report.issues and report.records[0]['native_identity']=='UNVERIFIED'
    assert not module.wrap_legacy(b'{}','unknown-legacy-algorithm','a'*64)['digest_verified']


def test_explicit_offline_root_and_no_links(tmp_path):
    root,index=make_snapshot(tmp_path/'offline');(root/'manifest.json').unlink()
    (root/'manifest.json').symlink_to('/etc/passwd')
    report=api().inspect_legacy(root)
    assert report.issues and not report.records


def test_old_issue_only_returns_mapping(github_case,tmp_path):
    from dataclasses import replace
    from chat_hpc_control.transports.github import GitHubGateway
    event,issue,site=github_case;root,index=make_snapshot(tmp_path/'offline')
    issue['body']='<!-- CHATGPT_QC_REQUEST_V1 -->\n{"version":1,"kind":"molpro","task_id":"synthetic-old-h2"}'
    site=replace(site,settings={**site.settings,'legacy_snapshot':str(root)})
    def dispatch(*args):pytest.fail('legacy request reached new broker submission')
    response=GitHubGateway(site,lambda n:issue,dispatch).dispatch(event)
    assert response.ok and response.data['mode']=='READ_ONLY_LEGACY'
    assert response.data['task_id']=='synthetic-old-h2' and not response.data['adoptable']
