"""Atomic immutable receipts and Linux process identity verification."""

import hashlib
import json
import os
from pathlib import Path
import tempfile

from ..contracts.codec import decode_json
from ..contracts.errors import ControlError
from ..contracts.execution import ExecutionObservation, RunHandle
from ..core.store import utc_now


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_once(path: Path, raw: bytes) -> bool:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".stage-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(name, path)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != raw:
                raise ControlError("INPUT_CHANGED", "immutable receipt or plan changed")
            return False
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return True
    finally:
        Path(name).unlink(missing_ok=True)


def write_receipt(root: Path, record: dict) -> None:
    kind = record.get("kind")
    if kind not in {"startup", "program-start", "terminal"}:
        raise ControlError("SCHEMA_INVALID", "unknown worker receipt kind")
    raw = json.dumps(record, sort_keys=True, ensure_ascii=False, allow_nan=False,
                     separators=(",", ":")).encode()
    write_once(root / (kind + ".json"), raw)


def process_identity(pid: int) -> dict:
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    stat = Path(f"/proc/{pid}/stat").read_text()
    tail = stat[stat.rfind(")") + 2:].split()
    command = Path(f"/proc/{pid}/cmdline").read_bytes()
    return {"pid": pid, "boot_id": boot, "start_time": tail[19],
            "command_sha256": hashlib.sha256(command).hexdigest()}


def verify_process(handle: RunHandle) -> ExecutionObservation:
    root = Path(handle.run_root)
    def unknown(reason):
        return ExecutionObservation("UNKNOWN", False, utc_now(), evidence={"reason": reason})
    try:
        start_path = root / "startup.json"
        if start_path.is_symlink() or digest_file(start_path) != handle.identity.get("startup_sha256"):
            return unknown("STARTUP_RECEIPT_CHANGED")
        startup = decode_json(start_path.read_bytes())
        if (any(startup["identity"].get(k) != handle.identity.get(k)
                for k in ("pid", "boot_id", "start_time", "command_sha256"))
                or startup["site_id"] != handle.site_id or startup["executor_id"] != handle.executor_id
                or digest_file(root / "approved-plan.json") != startup["plan_sha256"]):
            return unknown("WORKER_IDENTITY_MISMATCH")
        terminal_path = root / "terminal.json"
        if terminal_path.exists():
            if terminal_path.is_symlink():
                return unknown("TERMINAL_RECEIPT_CHANGED")
            terminal = decode_json(terminal_path.read_bytes())
            if (terminal["startup_sha256"] != handle.identity["startup_sha256"]
                    or terminal["plan_sha256"] != startup["plan_sha256"]
                    or terminal["manifest_sha256"] != startup["manifest_sha256"]
                    or terminal["run_id"] != startup["run_id"]
                    or terminal["reservation_id"] != startup["reservation_id"]):
                return unknown("TERMINAL_IDENTITY_MISMATCH")
            for record in terminal["logs"]:
                path = root / record["path"]
                if (record["path"] not in {"stdout.log", "stderr.log"} or path.is_symlink()
                        or path.stat().st_size != record["size"] or digest_file(path) != record["sha256"]):
                    return unknown("TERMINAL_LOG_CHANGED")
            return ExecutionObservation(terminal["execution_state"], True, terminal["observed_at"],
                                        terminal["exit_code"], terminal)
        current = process_identity(handle.identity["pid"])
        if any(current[k] != handle.identity.get(k) for k in current):
            return unknown("LIVE_PROCESS_IDENTITY_MISMATCH")
        state = "RUNNING" if (root / "program-start.json").is_file() else "QUEUED"
        return ExecutionObservation(state, True, utc_now(), evidence={"worker_identity": current})
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return unknown("WORKER_EVIDENCE_UNAVAILABLE")
