"""Single-writer SQLite reservations and append-only audit events."""

from dataclasses import asdict
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import threading
import uuid

from ..contracts.auth import CallContext
from ..contracts.codec import decode_json
from ..contracts.errors import ControlError
from ..contracts.execution import Reservation, RunHandle, SubmissionReceipt, SubmissionRequest
from .manifest import canonical_bytes

APPLICATION_ID = 0x43485043
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _reject_network_filesystem(root: Path):
    import sys
    if sys.platform == "linux":
        import ctypes
        buffer = ctypes.create_string_buffer(512)
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.statfs(os.fsencode(root), buffer) != 0:
            raise ControlError("RESOURCE_UNSUPPORTED", "state filesystem could not be verified")
        kind = ctypes.c_long.from_buffer(buffer).value
        if kind in {0x6969, 0x517B, 0xFF534D42}:
            raise ControlError("RESOURCE_UNSUPPORTED", "network state filesystems are unsupported")


class StateStore:
    def __init__(self, root, connection, lock_fd):
        self.root = root
        self.db = connection
        self.lock_fd = lock_fd
        self._mutex = threading.RLock()
        self._closed = False

    @classmethod
    def open(cls, root: Path):
        root = Path(root)
        if not root.is_absolute() or root.is_symlink():
            raise ControlError("SCHEMA_INVALID", "private state root must be absolute and not a link")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        _reject_network_filesystem(root)
        fd = os.open(root / "broker.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            raise ControlError("BROKER_ALREADY_RUNNING", "another broker owns this site") from exc
        path = root / "state.sqlite3"
        con = None
        try:
            existing = path.exists()
            if path.is_symlink() or (existing and not path.is_file()):
                raise ControlError("SCHEMA_INVALID", "state database is not a regular file")
            if not existing:
                created = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                os.close(created)
            con = sqlite3.connect(path, isolation_level=None, check_same_thread=False, timeout=30)
            app_id = con.execute("PRAGMA application_id").fetchone()[0]
            version = con.execute("PRAGMA user_version").fetchone()[0]
            if existing and (app_id != APPLICATION_ID or version != 1):
                raise ControlError("SCHEMA_INVALID", "refusing an unknown state database")
            if not existing:
                con.executescript(f"""
                    PRAGMA application_id={APPLICATION_ID};
                    PRAGMA user_version=1;
                    CREATE TABLE runs (
                      reservation_id TEXT PRIMARY KEY, run_id TEXT NOT NULL UNIQUE,
                      site_id TEXT NOT NULL, owner TEXT NOT NULL, idempotency_key TEXT NOT NULL,
                      fingerprint TEXT NOT NULL, request TEXT NOT NULL, execution_state TEXT NOT NULL,
                      receipt TEXT, observed_at TEXT, evidence TEXT NOT NULL DEFAULT '{{}}',
                      UNIQUE(site_id, owner, idempotency_key));
                    CREATE TABLE events (
                      event_id INTEGER PRIMARY KEY, run_id TEXT NOT NULL,
                      kind TEXT NOT NULL, observed_at TEXT NOT NULL, payload TEXT NOT NULL);
                """)
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=FULL")
            con.row_factory = sqlite3.Row
            return cls(root, con, fd)
        except Exception:
            if con is not None:
                con.close()
            os.close(fd)
            raise

    def close(self):
        with self._mutex:
            if not self._closed:
                self.db.close()
                os.close(self.lock_fd)
                self._closed = True

    def _reservation(self, row) -> Reservation:
        return Reservation(row["reservation_id"], row["run_id"], row["site_id"], row["owner"],
                           row["idempotency_key"], row["fingerprint"],
                           decode_json(row["request"].encode()), row["execution_state"])

    def find_key(self, site_id: str, owner: str, key: str) -> Reservation | None:
        with self._mutex:
            row = self.db.execute("SELECT * FROM runs WHERE site_id=? AND owner=? AND idempotency_key=?",
                                  (site_id, owner, key)).fetchone()
            return self._reservation(row) if row else None

    def reserve(self, request: SubmissionRequest, context: CallContext, fingerprint: str) -> Reservation:
        encoded = canonical_bytes(asdict(request)).decode()
        with self._mutex:
            old = self.find_key(request.site_id, context.principal, request.idempotency_key)
            if old:
                if old.fingerprint != fingerprint or canonical_bytes(old.request).decode() != encoded:
                    raise ControlError("IDEMPOTENCY_CONFLICT", "key is bound to another request")
                return old
            reservation_id, run_id = str(uuid.uuid4()), str(uuid.uuid4())
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.db.execute("INSERT INTO runs (reservation_id,run_id,site_id,owner,idempotency_key,"
                                "fingerprint,request,execution_state) VALUES (?,?,?,?,?,?,?,?)",
                                (reservation_id, run_id, request.site_id, context.principal,
                                 request.idempotency_key, fingerprint, encoded, "RESERVED"))
                self._event(run_id, "RESERVED", {"manifest_sha256": request.expected_manifest_sha256})
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise
            return self.find_key(request.site_id, context.principal, request.idempotency_key)

    def _event(self, run_id, kind, payload):
        encoded = json.dumps(payload, allow_nan=False, separators=(",", ":"))
        self.db.execute("INSERT INTO events(run_id,kind,observed_at,payload) VALUES(?,?,?,?)",
                        (run_id, kind, utc_now(), encoded))

    def get_run(self, run_id: str) -> dict:
        with self._mutex:
            row = self.db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not row:
                raise ControlError("NOT_FOUND", "run is unavailable")
            result = dict(row)
            result["request"] = decode_json(result["request"].encode())
            result["evidence"] = decode_json(result["evidence"].encode())
            return result

    def get_receipt(self, reservation: Reservation) -> SubmissionReceipt:
        row = self.get_run(reservation.run_id)
        if row["receipt"]:
            data = decode_json(row["receipt"].encode())
            handle = RunHandle(**data["handle"]) if data["handle"] else None
            return SubmissionReceipt(data["reservation_id"], data["run_id"], row["execution_state"],
                                     handle, tuple(data.get("evidence_refs", [])))
        return SubmissionReceipt(reservation.reservation_id, reservation.run_id, row["execution_state"])

    def record_receipt(self, reservation: Reservation, receipt: SubmissionReceipt):
        if (receipt.reservation_id != reservation.reservation_id or receipt.run_id != reservation.run_id
                or (receipt.handle and receipt.handle.site_id != reservation.site_id)):
            raise ControlError("JOB_IDENTITY_UNVERIFIED", "submission receipt belongs to another run")
        with self._mutex:
            current = self.get_run(reservation.run_id)
            if current["execution_state"] in TERMINAL:
                return
            encoded = json.dumps(asdict(receipt), allow_nan=False, separators=(",", ":"))
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.db.execute("UPDATE runs SET receipt=?,execution_state=?,observed_at=? WHERE run_id=?",
                                (encoded, receipt.execution_state, utc_now(), reservation.run_id))
                self._event(reservation.run_id, "SUBMISSION_RECEIPT", asdict(receipt))
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise

    def update_state(self, reservation_id: str, state: str, evidence: dict | None = None):
        with self._mutex:
            row = self.db.execute("SELECT * FROM runs WHERE reservation_id=?", (reservation_id,)).fetchone()
            if not row:
                raise ControlError("NOT_FOUND", "reservation unavailable")
            if row["execution_state"] in TERMINAL and state != row["execution_state"]:
                raise ControlError("STATE_CONFLICT", "terminal execution evidence is immutable")
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.db.execute("UPDATE runs SET execution_state=?,observed_at=?,evidence=? WHERE reservation_id=?",
                                (state, utc_now(), json.dumps(evidence or {}, allow_nan=False), reservation_id))
                self._event(row["run_id"], state, evidence or {})
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise

    def list_unresolved(self) -> list[Reservation]:
        with self._mutex:
            rows = self.db.execute("SELECT * FROM runs WHERE execution_state IN ('RESERVED','SUBMISSION_UNKNOWN')").fetchall()
            return [self._reservation(row) for row in rows]

    def list_runs(self) -> list[dict]:
        with self._mutex:
            ids = self.db.execute("SELECT run_id FROM runs ORDER BY rowid").fetchall()
            return [self.get_run(row[0]) for row in ids]
