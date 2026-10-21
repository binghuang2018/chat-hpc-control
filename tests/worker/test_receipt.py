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
