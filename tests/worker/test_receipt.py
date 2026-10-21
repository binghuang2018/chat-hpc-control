import importlib
import json

import pytest

from chat_hpc_control.contracts.errors import ControlError


def api():
    try:
        return importlib.import_module("chat_hpc_control.worker.receipt")
    except ModuleNotFoundError:
        pytest.fail("durable native worker receipts are missing")


def test_atomic_terminal_receipt_is_immutable(tmp_path):
    record = {"kind": "terminal", "exit_code": 0, "execution_state": "COMPLETED"}
    api().write_receipt(tmp_path, record)
    assert json.loads((tmp_path / "terminal.json").read_bytes()) == record
    api().write_receipt(tmp_path, record)
    with pytest.raises(ControlError, match="INPUT_CHANGED"):
        api().write_receipt(tmp_path, {**record, "exit_code": 1})
    assert (tmp_path / "terminal.json").stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.glob(".stage-*")) == []


def test_receipt_kind_cannot_escape_directory(tmp_path):
    with pytest.raises(ControlError, match="SCHEMA_INVALID"):
        api().write_receipt(tmp_path, {"kind": "../escape"})
    assert not (tmp_path.parent / "escape.json").exists()


def test_worker_rechecks_extra_native_runtime_files(sample_task,tmp_path):
    from dataclasses import replace
    import hashlib,sys,uuid
    from pathlib import Path
    from chat_hpc_control.contracts.codec import parse_task
    from chat_hpc_control.contracts.config import SiteConfig,RuntimeConfig,ExecutorConfig
    from chat_hpc_control.contracts.execution import ExecutionPlan,ApprovedExecutionPlan
    from chat_hpc_control.contracts.plugins import PluginInfo,ProbeReport
    from chat_hpc_control.contracts.task import ResolvedTask
    from chat_hpc_control.core.manifest import build_manifest,freeze
    from chat_hpc_control.worker.launcher import validate_approval
    extra=tmp_path/'native-data';extra.write_text('one')
    task=parse_task(json.dumps(sample_task).encode())
    site=SiteConfig('example-site',tmp_path/'site',{}, {'pyscf':RuntimeConfig(sys.executable,options={'fingerprint_paths':[str(extra)]})},ExecutorConfig('local','example'))
    resolved=ResolvedTask(task,{'job.py':b'print(1)'},{'kind':'synthetic'})
    manifest=build_manifest(resolved,PluginInfo('pyscf','synthetic','1','a'*64),
         ProbeReport(True,'synthetic',{'program_sha256':hashlib.sha256(Path(sys.executable).resolve().read_bytes()).hexdigest()}),site)
    frozen=freeze(resolved,site,manifest=manifest)
    run_id=str(uuid.uuid4());plan=ExecutionPlan((sys.executable,'-B','job.py'),site.root/'runs'/run_id/'work',{},(),task.resources,'pyscf')
    approved=ApprovedExecutionPlan(plan,site.site_id,run_id,frozen.manifest_sha256,frozen.input_root)
    validate_approval(approved)
    extra.write_text('two')
    with pytest.raises(ControlError,match='INPUT_CHANGED'):validate_approval(approved)


def test_worker_rechecks_approval_after_waiting_for_slot(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from chat_hpc_control.worker import main as worker
    from chat_hpc_control.contracts.errors import ControlError
    approved=SimpleNamespace(site_id='synthetic',run_id='run-1',manifest_sha256='a'*64,
                             plan=SimpleNamespace(resources=SimpleNamespace(walltime_seconds=None)))
    launch=tmp_path/'launch.json';launch.write_text(json.dumps({'approved':{},'reservation_id':'r','executor_id':'local','queue_root':str(tmp_path/'queue'),'max_concurrent':1}))
    monkeypatch.setattr(worker,'from_wire',lambda *_:approved)
    monkeypatch.setattr(worker,'process_identity',lambda *_:{'synthetic':True})
    queued=False;checks=[]
    def validate(_):
        checks.append(queued)
        if queued:raise ControlError('INPUT_CHANGED','runtime changed while queued')
        return {'files':[]}
    monkeypatch.setattr(worker,'validate_approval',validate)
    def slot(*_):
        nonlocal queued
        queued=True
        return __import__('os').open(tmp_path/'slot',__import__('os').O_CREAT|__import__('os').O_RDWR,0o600)
    monkeypatch.setattr(worker,'_slot',slot)
    assert worker.main(['--launch-file',str(launch)])==1
    assert checks==[False,True], 'approval was not repeated after the queue wait'
    assert json.loads((tmp_path/'terminal.json').read_text())['reason']=='WORKER_VALIDATION_OR_EXECUTION_ERROR'
