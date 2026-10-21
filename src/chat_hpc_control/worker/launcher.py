"""Launch one fixed installed worker per immutable reservation."""

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

from ..contracts.codec import decode_json
from ..contracts.errors import ControlError
from ..contracts.execution import ApprovedExecutionPlan, RunHandle, SubmissionReceipt
from ..plugins.wire import to_wire
from ..sources.bundle import read_verified
from ..core.manifest import execution_identity
from .receipt import digest_file, verify_process, write_once


def validate_approval(approved: ApprovedExecutionPlan):
    root = approved.input_root
    if root.is_symlink() or root.name != "files" or root.parent.name != approved.manifest_sha256:
        raise ControlError("INPUT_CHANGED", "input root is not the approved content identity")
    raw = (root.parent / "manifest.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != approved.manifest_sha256:
        raise ControlError("INPUT_CHANGED", "input manifest changed")
    manifest = decode_json(raw)
    if (manifest.get("schema") != "chat-hpc-control/task-manifest/v1"
            or manifest["site"]["site_id"] != approved.site_id
            or manifest.get("control") != execution_identity()
            or manifest["task"]["resources"] != asdict(approved.plan.resources)):
        raise ControlError("INPUT_CHANGED", "execution manifest is not an approved task")
    read_verified(root, manifest["files"])
    runtime = manifest["program"]["runtime"]
    executable = Path(runtime["executable"])
    if digest_file(executable.resolve()) != manifest["program"]["identity"].get("program_sha256"):
        raise ControlError("INPUT_CHANGED", "configured native executable changed")
    trusted = {executable.resolve()}
    if runtime.get("mpi_argv") and Path(runtime["mpi_argv"][0]).is_absolute():
        trusted.add(Path(runtime["mpi_argv"][0]).resolve())
    if not approved.plan.argv or Path(approved.plan.argv[0]).resolve() not in trusted:
        raise ControlError("SCHEMA_INVALID", "execution argv does not start with an approved executable")
    return manifest


def prepare_launch(approved, reservation_id, *, executor_id, queue_root, max_concurrent=1, output_limit=268435456):
    validate_approval(approved)
    root = approved.plan.cwd
    run_root = root
    while run_root.name != approved.run_id and run_root.parent != run_root:
        run_root = run_root.parent
    if run_root.name != approved.run_id or not re.fullmatch(r"[0-9a-f-]{36}", approved.run_id):
        raise ControlError("SCHEMA_INVALID", "execution work directory is not inside its run")
    if not root.resolve().is_relative_to(run_root.resolve()):
        raise ControlError("SCHEMA_INVALID", "work directory escapes run")
    run_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    launch = {"schema": "chat-hpc-control/launch/v1", "approved": to_wire(approved),
              "reservation_id": reservation_id, "executor_id": executor_id,
              "queue_root": str(queue_root), "max_concurrent": max_concurrent, "output_limit": output_limit}
    path = run_root / "approved-plan.json"
    created = write_once(path, json.dumps(launch, sort_keys=True, allow_nan=False,
                                        separators=(",", ":")).encode())
    return path, created


def receipt_from_start(path: Path, job_id: str | None = None) -> SubmissionReceipt:
    root = path.parent
    startup = decode_json((root / "startup.json").read_bytes())
    identity = {**startup["identity"], "startup_sha256": digest_file(root / "startup.json")}
    handle = RunHandle(startup["site_id"], startup["executor_id"],
                       job_id or str(identity["pid"]), str(root), identity)
    observed = verify_process(handle)
    return SubmissionReceipt(startup["reservation_id"], startup["run_id"], observed.execution_state, handle)


def launch(plan: ApprovedExecutionPlan, reservation_id: str, *, executor_id="local",
           queue_root: Path | None = None, max_concurrent=1, output_limit=268435456) -> SubmissionReceipt:
    path, created = prepare_launch(plan, reservation_id, executor_id=executor_id,
                                  queue_root=queue_root or plan.plan.cwd.parent / "queue",
                                  max_concurrent=max_concurrent, output_limit=output_limit)
    root = path.parent
    if not created:
        if (root / "startup.json").is_file():
            return receipt_from_start(path)
        raise ControlError("SUBMISSION_UNKNOWN", "launch intent already exists without a confirmed worker")
    for name in ("home", "tmp"):
        (root / name).mkdir(mode=0o700, exist_ok=True)
    environment = {"PATH": os.defpath, "HOME": str(root / "home"), "TMPDIR": str(root / "tmp"),
                   "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    log_fd = os.open(root / "worker.log", os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
    with os.fdopen(log_fd, "wb") as log:
        process = subprocess.Popen([sys.executable, "-I", "-B", "-m", "chat_hpc_control.worker.main",
                                    "--launch-file", str(path)], stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=log, env=environment, cwd=root,
                                   close_fds=True, start_new_session=True)
    threading.Thread(target=process.wait, name=f"chc-worker-reap-{process.pid}", daemon=True).start()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if (root / "startup.json").is_file():
            return receipt_from_start(path)
        if process.poll() is not None:
            break
        time.sleep(.025)
    raise ControlError("SUBMISSION_UNKNOWN", "worker launch has no confirmed startup receipt")
