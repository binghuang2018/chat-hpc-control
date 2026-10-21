from dataclasses import replace
import importlib

import pytest

from chat_hpc_control.contracts.tools import ToolCall
from tests.core.test_idempotency import setup_broker, request


def service(broker):
    try:
        cls = importlib.import_module("chat_hpc_control.core.service").ToolService
    except ModuleNotFoundError:
        pytest.fail("six-tool service is missing")
    return cls(broker)


def test_tool_allowlist(setup_broker):
    broker, task, ctx, store, engine, executor = setup_broker
    s = service(broker)
    answer = s.handle(ToolCall("shell", {"command": "whoami"}), ctx)
    assert not answer.ok
    assert answer.error["code"] == "SCHEMA_INVALID"


def test_validate_and_submit_tool_contract(setup_broker):
    broker, task, ctx, store, engine, executor = setup_broker
    s = service(broker)
    result = s.handle(ToolCall("validate_task", {"site_id": ctx.site_id, "task": task.to_dict()}), ctx)
    assert result.ok and result.data["valid"]
    assert "manifest" not in result.data
    submission = s.handle(ToolCall("submit_task", {
        "site_id": ctx.site_id, "task": result.data["task"], "expected_manifest_sha256": result.data["manifest_sha256"],
        "idempotency_key": "tool-intent-1", "rerun_of": None}), ctx)
    assert submission.ok
    assert submission.data["execution_state"] == "QUEUED"
    assert len(executor.submissions) == 1


def test_read_has_no_side_effects(setup_broker):
    broker, task, ctx, store, engine, executor = setup_broker
    s = service(broker)
    ctx = replace(ctx, scopes=ctx.scopes | {"results:read"})
    receipt = broker.submit(request(broker, task, ctx), ctx)
    status = s.handle(ToolCall("get_task_status", {"site_id": ctx.site_id, "run_id": receipt.run_id}), ctx)
    assert status.ok and status.data["execution_state"] == "QUEUED"
    result = s.handle(ToolCall("get_task_results", {"site_id": ctx.site_id, "run_id": receipt.run_id,
        "collection_id": None, "fields": [], "cursor": None, "page_size": 10}), ctx)
    assert result.ok and result.data["summary"]["data_ready"] is False
    manifest = s.handle(ToolCall("get_result_manifest", {"site_id": ctx.site_id, "run_id": receipt.run_id,
                                                       "collection_id": None}), ctx)
    assert manifest.ok and manifest.data["collection_state"] == "PENDING"
    assert len(executor.submissions) == 1


@pytest.mark.parametrize("field", ["principal", "scopes", "shell"])
def test_identity_and_unknown_fields_are_not_tool_parameters(setup_broker, field):
    broker, task, ctx, store, engine, executor = setup_broker
    args = {"site_id": ctx.site_id, "task": task.to_dict(), field: "spoofed"}
    answer = service(broker).handle(ToolCall("validate_task", args), ctx)
    assert not answer.ok and answer.error["code"] == "SCHEMA_INVALID"


def test_cross_site_tool_denied(setup_broker):
    broker, task, ctx, store, engine, executor = setup_broker
    answer = service(broker).handle(ToolCall("get_task_status", {"site_id": "other-site", "run_id": "x"}), ctx)
    assert not answer.ok and answer.error["code"] == "AUTH_DENIED"
