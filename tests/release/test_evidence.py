import importlib.util,json,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]


def tool(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_existing_evidence_name_cannot_be_overwritten(tmp_path,monkeypatch):
    record=tmp_path/'same.json';record.write_text('{"status":"PASS","command":["previous"]}')
    log=tmp_path/'same.log';log.write_text('previous verified log')
    monkeypatch.setattr(sys,'argv',['record_validation','--name','same','--evidence',str(tmp_path),'--',sys.executable,'-c','print("new")'])
    with pytest.raises((FileExistsError,SystemExit)):tool('record_validation').main()
    assert log.read_text()=='previous verified log'
    assert json.loads(record.read_text())['command']==['previous']


def test_source_change_retains_log_without_creating_pass(tmp_path,monkeypatch):
    module=tool('record_validation');digests=iter(['old','changed'])
    monkeypatch.setattr(module,'source_digest',lambda:next(digests))
    monkeypatch.setattr(sys,'argv',['record_validation','--name','changed','--evidence',str(tmp_path),'--',sys.executable,'-c','print("synthetic changed-source check")'])
    with pytest.raises(RuntimeError,match='source changed'):module.main()
    assert (tmp_path/'changed.log').exists() and not (tmp_path/'changed.json').exists()


def test_release_rejects_changed_log(tmp_path):
    import hashlib
    dist=tmp_path/'dist';dist.mkdir();(dist/'synthetic.whl').write_bytes(b'synthetic')
    evidence=tmp_path/'evidence';evidence.mkdir();log=evidence/'one.log';log.write_text('old verified log')
    record={'name':'one','status':'PASS','command':['synthetic'],'environment':'synthetic','versions':{'python':'synthetic'},'exit_code':0,'log':'one.log','log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'summary':'synthetic'}
    (evidence/'one.json').write_text(json.dumps(record));log.write_text('new failed command log')
    with pytest.raises(ValueError,match='log'):tool('release_manifest').build_release_manifest(dist,evidence)
