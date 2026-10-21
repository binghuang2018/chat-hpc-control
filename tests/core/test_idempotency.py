import concurrent.futures
import importlib
import io
import json
import sys
import tarfile

import pytest

from chat_hpc_control.contracts.auth import CallContext
from chat_hpc_control.contracts.codec import parse_task
from chat_hpc_control.contracts.config import ExecutorConfig, RuntimeConfig, SiteConfig
from chat_hpc_control.contracts.errors import ControlError
from chat_hpc_control.contracts.execution import SubmissionRequest
from chat_hpc_control.sources.base import SourceResolver
from chat_hpc_control.sources.bundle import BundleStore


def broker_api():
    try:
        return importlib.import_module("chat_hpc_control.core.broker")
    except ModuleNotFoundError:
        pytest.fail("durable idempotent broker implementation is missing")


@pytest.fixture
def setup_broker(tmp_path, sample_task):
    broker_api()
    from chat_hpc_control.core.store import StateStore
    from tests.fakes import DemoEngine, RecordingExecutor
    site = SiteConfig("example-site", tmp_path / "site", {}, {"demo": RuntimeConfig(sys.executable)},
                       ExecutorConfig("local", "example-local"))
    archive = tmp_path / "input.tar"
    with tarfile.open(archive, "w") as arc:
        rec = tarfile.TarInfo("job.py"); rec.size = 9
        arc.addfile(rec, io.BytesIO(b"print(1)\n"))
    bundle = BundleStore(site).import_tar(archive)
    sample_task["engine_id"] = "demo"
    sample_task["source"]["bundle_id"] = bundle
    task = parse_task(json.dumps(sample_task).encode())
    ctx = CallContext("alice", site.site_id, frozenset({"tasks:submit", "tasks:validate", "tasks:read"}),
                      engines=frozenset({"demo"}))
    store = StateStore.open(site.root)
    engine, executor = DemoEngine(), RecordingExecutor()
    broker = broker_api().Broker(site, store, SourceResolver(), {"demo": engine}, executor)
    try:
        yield broker, task, ctx, store, engine, executor
    finally:
        store.close()


def request(broker, task, ctx, key="intent-1", rerun_of=None):
    validated = broker.validate(task, ctx)
    return SubmissionRequest(ctx.site_id, validated.task, validated.manifest_sha256, key, rerun_of)


def test_same_key_once(setup_broker):
    broker, task, ctx, store, engine, executor = setup_broker
    req = request(broker, task, ctx)
    one = broker.submit(req, ctx)
    two = broker.submit(req, ctx)
    assert one.run_id == two.run_id
    assert len(executor.submissions) == 1


def test_concurrent_duplicates(setup_broker):
    broker, task, ctx, store, engine, executor = setup_broker
    req = request(broker, task, ctx)
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        receipts = list(pool.map(lambda _: broker.submit(req, ctx), range(8)))
    assert len({r.run_id for r in receipts}) == 1
    assert len(executor.submissions) == 1


def test_conflict(setup_broker):
    broker, task, ctx, store, engine, executor = setup_broker
    req = request(broker, task, ctx)
    broker.submit(req, ctx)
    from dataclasses import replace
    with pytest.raises(ControlError, match="IDEMPOTENCY_CONFLICT"):
        broker.submit(replace(req, expected_manifest_sha256="b" * 64), ctx)
    assert len(executor.submissions) == 1


def test_retry_after_environment_update(setup_broker):
    broker, task, ctx, store, engine, executor = setup_broker
    req = request(broker, task, ctx)
    before = broker.submit(req, ctx)
    probes = engine.probe_calls
    engine.version = "updated-runtime"
    after = broker.submit(req, ctx)
    assert after.run_id == before.run_id
    assert engine.probe_calls == probes
    assert len(executor.submissions) == 1


def test_expected_manifest_changed(setup_broker):
    broker, task, ctx, store, engine, executor = setup_broker
    req = request(broker, task, ctx)
    engine.version = "updated-runtime"
    with pytest.raises(ControlError, match="INPUT_CHANGED"):
        broker.submit(req, ctx)
    assert executor.submissions == []
    assert store.list_unresolved() == []


def test_rerun_is_explicit_and_preserves_original(setup_broker):
    broker, task, ctx, store, engine, executor = setup_broker
    one = broker.submit(request(broker, task, ctx), ctx)
    two = broker.submit(request(broker, task, ctx, "intent-2", one.run_id), ctx)
    assert two.run_id != one.run_id
    assert broker.get_status(one.run_id, ctx).execution_state == "QUEUED"
    assert len(executor.submissions) == 2


def test_run_ownership_is_not_a_guess(setup_broker):
    broker, task, ctx, store, engine, executor = setup_broker
    one = broker.submit(request(broker, task, ctx), ctx)
    from dataclasses import replace
    with pytest.raises(ControlError, match="AUTH_DENIED"):
        broker.get_status(one.run_id, replace(ctx, principal="bob"))


def test_unapproved_executable_never_reaches_executor(setup_broker, monkeypatch):
    broker, task, ctx, store, engine, executor = setup_broker
    from dataclasses import replace
    original = engine.prepare
    def wrong_program(frozen, context):
        return replace(original(frozen, context), argv=("/bin/sh", "-c", "echo unapproved"))
    monkeypatch.setattr(engine, "prepare", wrong_program)
    req = request(broker, task, ctx)
    with pytest.raises(ControlError, match="SCHEMA_INVALID"):
        broker.submit(req, ctx)
    assert executor.submissions == []
