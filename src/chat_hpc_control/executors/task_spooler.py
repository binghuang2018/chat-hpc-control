"""Dedicated Task Spooler queue with durable instance and per-run identities."""

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import struct
import sys
import time

from ..contracts.codec import decode_json
from ..contracts.errors import ControlError
from ..contracts.execution import ExecutionObservation, ReconciliationReport, RunHandle, SubmissionReceipt
from ..core.store import utc_now
from ..worker.launcher import prepare_launch, receipt_from_start
from ..worker.receipt import digest_file, process_identity, write_once
from .local import LocalExecutor
from .ts_cli import TsCli


def packed(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class TaskSpoolerExecutor(LocalExecutor):
    def __init__(self, site):
        super().__init__(site)
        self.socket_path = Path(site.executor.options.get("socket_path", site.root / "tsp.sock"))
        self.instance_path = site.root / "task-spooler-instance.json"
        self.cli = TsCli(Path(site.executor.options["executable"]), site.root)

    def _instance(self):
        details = self.socket_path.stat()
        with socket.socket(socket.AF_UNIX) as peer:
            peer.settimeout(2)
            peer.connect(str(self.socket_path))
            pid, uid, gid = struct.unpack("3i", peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if uid != os.getuid():
            raise ControlError("JOB_IDENTITY_UNVERIFIED", "queue server belongs to another uid")
        return {"site_id": self.site.site_id, "executor_id": self.info().executor_id,
                "socket": str(self.socket_path), "device": details.st_dev, "inode": details.st_ino,
                "server": process_identity(pid), "uid": uid,
                "binary_sha256": digest_file(self.cli.executable.resolve())}

    def _verify_queue(self):
        if (not self.instance_path.exists() or self.instance_path.is_symlink()
                or decode_json(self.instance_path.read_bytes()) != self._instance()):
            raise ControlError("JOB_IDENTITY_UNVERIFIED", "queue instance no longer matches durable identity")

    def ensure_queue(self):
        if self.instance_path.exists():
            self._verify_queue()
            return
        if self.socket_path.exists():
            raise ControlError("JOB_IDENTITY_UNVERIFIED", "unmanaged queue socket cannot be adopted")
        self.cli.run(["-S", str(self.site.executor.options["max_cpus"])], self.socket_path)
        write_once(self.instance_path, packed(self._instance()))

    def _command(self, path):
        return [sys.executable, "-I", "-B", "-m", "chat_hpc_control.worker.main", "--launch-file", str(path)]

    def _job_command(self, job_id):
        data = self.cli.run(["-i", str(job_id)], self.socket_path).decode("utf-8", "strict")
        rows = [line.removeprefix("Command: ") for line in data.splitlines() if line.startswith("Command: ")]
        if len(rows) != 1:
            raise ControlError("JOB_IDENTITY_UNVERIFIED", "queue job has no full command identity")
        return rows[0]

    def _save(self, path, job_id):
        launch = decode_json(path.read_bytes())
        approved = launch["approved"]
        command = self._job_command(job_id)
        if command != " ".join(self._command(path)):
            raise ControlError("JOB_IDENTITY_UNVERIFIED", "queue command differs from approved worker")
        record = {"site_id": approved["site_id"], "executor_id": self.info().executor_id,
                  "run_id": approved["run_id"], "reservation_id": launch["reservation_id"],
                  "manifest_sha256": approved["manifest_sha256"], "job_id": str(job_id),
                  "queue_instance_sha256": digest_file(self.instance_path),
                  "queue_command_sha256": hashlib.sha256(command.encode()).hexdigest()}
        write_once(path.parent / "scheduler-receipt.json", packed(record))
        return self._receipt(path.parent)

    def _receipt(self, root):
        record = decode_json((root / "scheduler-receipt.json").read_bytes())
        handle = RunHandle(record["site_id"], record["executor_id"], record["job_id"], str(root),
                           {**record, "scheduler_sha256": digest_file(root / "scheduler-receipt.json")})
        observation = self.query(handle)
        return SubmissionReceipt(record["reservation_id"], record["run_id"], observation.execution_state, handle)

    def submit(self, plan, reservation_id):
        self.ensure_queue()
        path, created = prepare_launch(plan, reservation_id, executor_id=self.info().executor_id,
                                      queue_root=self.site.root / "ts-worker-slots",
                                      max_concurrent=self.site.executor.options.get("max_concurrent", 1),
                                      output_limit=self.site.limits.get("max_output_bytes", 268435456))
        if not created:
            if (path.parent / "scheduler-receipt.json").exists():
                return self._receipt(path.parent)
            raise ControlError("SUBMISSION_UNKNOWN", "existing enqueue intent requires reconciliation")
        raw = self.cli.run(["-N", str(plan.plan.resources.cpus), "-L", "chc-" + reservation_id,
                            *self._command(path)], self.socket_path).decode().strip()
        if not re.fullmatch(r"[0-9]+", raw):
            raise ControlError("SUBMISSION_UNKNOWN", "enqueue response lacks a job id")
        self.ensure_queue()
        return self._save(path, raw)

    def query(self, handle):
        root = Path(handle.run_root)
        def unknown(reason):
            return ExecutionObservation("UNKNOWN", False, utc_now(), evidence={"reason": reason})
        try:
            if (handle.site_id != self.site.site_id or handle.executor_id != self.info().executor_id
                    or root.parent != self.site.root / "runs" or root.is_symlink()):
                return unknown("HANDLE_SCOPE_MISMATCH")
            receipt = root / "scheduler-receipt.json"
            record = decode_json(receipt.read_bytes())
            if (receipt.is_symlink() or digest_file(receipt) != handle.identity["scheduler_sha256"]
                    or any(record[key] != handle.identity.get(key) for key in record)
                    or record["job_id"] != handle.job_id or record["run_id"] != root.name):
                return unknown("SCHEDULER_RECEIPT_CHANGED")
            startup = root / "startup.json"
            if startup.exists():
                start = decode_json(startup.read_bytes())
                if any(start[key] != record[key] for key in ("run_id", "reservation_id", "manifest_sha256")):
                    return unknown("WORKER_RESERVATION_MISMATCH")
                if (root / "terminal.json").exists():
                    local = receipt_from_start(root / "approved-plan.json")
                    return super().query(local.handle)
            self._verify_queue()
            if digest_file(self.instance_path) != record["queue_instance_sha256"]:
                return unknown("QUEUE_INSTANCE_CHANGED")
            command = self._job_command(handle.job_id)
            if hashlib.sha256(command.encode()).hexdigest() != record["queue_command_sha256"]:
                return unknown("QUEUE_COMMAND_CHANGED")
            if startup.exists():
                return super().query(receipt_from_start(root / "approved-plan.json").handle)
            return ExecutionObservation("QUEUED", True, utc_now())
        except (OSError, ValueError, KeyError, TypeError):
            return unknown("SCHEDULER_EVIDENCE_UNAVAILABLE")

    def reconcile(self, reservation):
        root = self.site.root / "runs" / reservation.run_id
        path = root / "approved-plan.json"
        try:
            if (root / "scheduler-receipt.json").exists():
                receipt = self._receipt(root)
                if receipt.reservation_id != reservation.reservation_id:
                    return ReconciliationReport("UNKNOWN")
                return ReconciliationReport("SUBMITTED", receipt)
            if not path.exists():
                return ReconciliationReport("NOT_SUBMITTED")
            self._verify_queue()
            rows = self.cli.run(["-l"], self.socket_path).decode()
            ids = re.findall(r"(?m)^([0-9]+)\s", rows)
            matches = [job for job in ids if self._job_command(job) == " ".join(self._command(path))]
            if len(matches) == 1:
                return ReconciliationReport("SUBMITTED", self._save(path, matches[0]))
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return ReconciliationReport("UNKNOWN")
