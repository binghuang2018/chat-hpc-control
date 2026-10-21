import importlib
import json
import os
from pathlib import Path
import sys

import pytest

from chat_hpc_control.contracts.errors import ControlError


def api():
    try:
        return importlib.import_module("chat_hpc_control.executors.ts_cli")
    except ModuleNotFoundError:
        pytest.fail("controlled task-spooler CLI is missing")


def test_ts_cli_environment_and_explicit_socket(tmp_path, monkeypatch):
    program = tmp_path / "fake-ts"
    program.write_text(f"#!{sys.executable}\nimport os,json\nprint(json.dumps(dict(os.environ)))\n")
    program.chmod(0o700)
    monkeypatch.setenv("GITHUB_TOKEN", "synthetic-not-real")
    result = api().TsCli(program, tmp_path).run(["-V"], tmp_path / "tsp.sock")
    data = json.loads(result)
    assert "GITHUB_TOKEN" not in data
    assert data["TS_SOCKET"] == str(tmp_path / "tsp.sock")
    assert not (tmp_path / "tsp.sock").exists()


def test_ts_read_cannot_start_an_unconfigured_queue(tmp_path):
    cli = api().TsCli(Path(sys.executable), tmp_path)
    with pytest.raises(ControlError, match="JOB_IDENTITY_UNVERIFIED"):
        cli.run(["-l"], tmp_path / "absent.sock")
    assert not (tmp_path / "absent.sock").exists()


def test_unknown_ts_command_and_outside_socket_rejected(tmp_path):
    cli = api().TsCli(Path(sys.executable), tmp_path)
    with pytest.raises(ControlError, match="SCHEMA_INVALID"):
        cli.run(["/bin/sh", "-c", "echo bad"], tmp_path / "tsp.sock")
    with pytest.raises(ControlError, match="SCHEMA_INVALID"):
        cli.run(["-V"], tmp_path.parent / "unrelated.sock")
