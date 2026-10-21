import importlib
import importlib.util
import json

import pytest


def codec():
    assert importlib.util.find_spec("chat_hpc_control") is not None, "v1 contracts are not implemented"
    return importlib.import_module("chat_hpc_control.contracts.codec")


@pytest.mark.parametrize("field", ["cpus", "memory_mib", "walltime_seconds"])
def test_required_resources(sample_task, field):
    del sample_task["resources"][field]
    with pytest.raises(ValueError, match="SCHEMA_INVALID"):
        codec().parse_task(json.dumps(sample_task).encode())


@pytest.mark.parametrize("value", [1.5, True, 0, -1, 2**53])
def test_task_numbers(sample_task, value):
    sample_task["resources"]["cpus"] = value
    with pytest.raises(ValueError, match="SCHEMA_INVALID"):
        codec().parse_task(json.dumps(sample_task).encode())


def test_duplicate_keys():
    with pytest.raises(ValueError, match="SCHEMA_INVALID"):
        codec().decode_json(b'{"kind":"a","kind":"b"}')


@pytest.mark.parametrize("raw", [b'{"v":NaN}', b'{"v":Infinity}', b'{"v":1e999}'])
def test_results_reject_nonfinite(raw):
    with pytest.raises(ValueError, match="SCHEMA_INVALID"):
        codec().decode_json(raw)


def test_results_allow_finite_float():
    assert codec().decode_json(b'{"energy":-75.1}') == {"energy": -75.1}


def test_null_contract(sample_task):
    task = codec().parse_task(json.dumps(sample_task).encode())
    assert task.expected_results is None
    assert task.resources.walltime_seconds is None
    assert task.to_dict() == sample_task


@pytest.mark.parametrize("mutation", ["extra", "unknown_source", "bad_engine", "float_option", "surrogate"])
def test_invalid_task_variants(sample_task, mutation):
    if mutation == "extra":
        sample_task["principal"] = "admin"
    elif mutation == "unknown_source":
        sample_task["source"] = {"kind": "url", "url": "file:///etc/passwd"}
    elif mutation == "bad_engine":
        sample_task["engine_id"] = "../../python"
    elif mutation == "float_option":
        sample_task["engine_options"] = {"threshold": 0.01}
    else:
        sample_task["task_id"] = "\ud800"
    with pytest.raises(ValueError, match="SCHEMA_INVALID"):
        codec().parse_task(json.dumps(sample_task).encode())


def test_unknown_nested_fields(sample_task):
    sample_task["resources"]["shell"] = "echo bad"
    with pytest.raises(ValueError, match="SCHEMA_INVALID"):
        codec().parse_task(json.dumps(sample_task).encode())


def test_tool_response_envelope():
    c = codec()
    from chat_hpc_control.contracts.tools import ToolResponse
    encoded = c.encode_response(ToolResponse(request_id="request-1", ok=True, data={"state": "RUNNING"}))
    assert json.loads(encoded) == {
        "schema": "chat-hpc-control/tool-response/v1",
        "request_id": "request-1",
        "ok": True,
        "data": {"state": "RUNNING"},
        "error": None,
    }
