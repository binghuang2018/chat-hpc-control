import importlib
from pathlib import Path
import sqlite3

import pytest

from chat_hpc_control.contracts.errors import ControlError
from tests.core.test_idempotency import setup_broker, request


def store_api():
    try:
        return importlib.import_module("chat_hpc_control.core.store")
    except ModuleNotFoundError:
        pytest.fail("persistent reservation store is missing")


def test_foreign_sqlite_is_not_overwritten(tmp_path):
    cls = store_api().StateStore
    db = tmp_path / "state.sqlite3"
    with sqlite3.connect(db) as con:
        con.execute("create table unrelated (value text)")
    old = db.read_bytes()
    with pytest.raises(ControlError, match="SCHEMA_INVALID"):
        cls.open(tmp_path)
    assert db.read_bytes() == old


def test_single_writer_lock(tmp_path):
    one = store_api().StateStore.open(tmp_path)
    try:
        with pytest.raises(ControlError, match="BROKER_ALREADY_RUNNING"):
            store_api().StateStore.open(tmp_path)
    finally:
        one.close()


def test_lost_native_response_does_not_resubmit(setup_broker):
    broker, task, ctx, store, engine, executor = setup_broker
    req = request(broker, task, ctx)
    executor.lose_response = True
    with pytest.raises(ControlError, match="SUBMISSION_UNKNOWN"):
        broker.submit(req, ctx)
    unknown = broker.submit(req, ctx)
    assert unknown.execution_state == "SUBMISSION_UNKNOWN"
    assert len(executor.submissions) == 1
    reservation = store.list_unresolved()[0]
    found = executor.reconcile(reservation)
    store.record_receipt(reservation, found.receipt)
    assert broker.submit(req, ctx).execution_state == "QUEUED"
    assert len(executor.submissions) == 1


def test_receipt_write_crash_survives_reopen(setup_broker, monkeypatch):
    broker, task, ctx, store, engine, executor = setup_broker
    req = request(broker, task, ctx)
    original = store.record_receipt
    def crash(*args):
        raise OSError("simulated disk error after native submission")
    monkeypatch.setattr(store, "record_receipt", crash)
    with pytest.raises(ControlError, match="SUBMISSION_UNKNOWN"):
        broker.submit(req, ctx)
    monkeypatch.setattr(store, "record_receipt", original)
    from chat_hpc_control.core.store import StateStore
    from chat_hpc_control.core.broker import Broker
    store.close()
    reopened = StateStore.open(broker.site.root)
    try:
        restored = Broker(broker.site, reopened, broker.resolver, broker.engines, executor)
        assert restored.submit(req, ctx).execution_state == "SUBMISSION_UNKNOWN"
        reservation = reopened.list_unresolved()[0]
        reopened.record_receipt(reservation, executor.reconcile(reservation).receipt)
        assert restored.submit(req, ctx).execution_state == "QUEUED"
        assert len(executor.submissions) == 1
    finally:
        reopened.close()


def test_crash_after_reservation_never_blindly_resubmits(setup_broker, monkeypatch):
    broker, task, ctx, store, engine, executor = setup_broker
    req = request(broker, task, ctx)
    def crash_before_launch(*args):
        raise SystemExit("simulated process termination before executor submit")
    monkeypatch.setattr(engine, "prepare", crash_before_launch)
    with pytest.raises(SystemExit):
        broker.submit(req, ctx)
    restored = broker.submit(req, ctx)
    assert restored.execution_state == "RESERVED"
    assert executor.submissions == []
    reservation = store.list_unresolved()[0]
    assert executor.reconcile(reservation).outcome == "NOT_SUBMITTED"


def test_no_read_scope_is_denied_before_existence_probe(setup_broker):
    broker, task, ctx, store, engine, executor = setup_broker
    from dataclasses import replace
    with pytest.raises(ControlError, match="AUTH_DENIED"):
        broker.get_status("nonexistent", replace(ctx, scopes=frozenset()))
