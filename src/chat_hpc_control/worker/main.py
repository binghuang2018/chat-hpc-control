"""A standalone worker that survives the submitting client and broker."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading
import time

from ..contracts.codec import decode_json
from ..contracts.execution import ApprovedExecutionPlan
from ..core.store import utc_now
from ..plugins.wire import from_wire
from ..sources.base import checked_paths
from .launcher import validate_approval
from .receipt import digest_file, process_identity, write_receipt


def _slot(queue_root, count, cancelled):
    queue_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    while not cancelled.is_set():
        for index in range(count):
            fd = os.open(queue_root / f"slot-{index}.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except BlockingIOError:
                os.close(fd)
        cancelled.wait(.1)
    return None


def _terminate(program):
    if program is None or program.poll() is not None:
        return
    try:
        os.killpg(program.pid, signal.SIGTERM)
        program.wait(timeout=2)
    except subprocess.TimeoutExpired:
        os.killpg(program.pid, signal.SIGKILL)
        program.wait()
    except ProcessLookupError:
        program.wait()


def _has_marker(path, marker):
    if path.is_symlink() or not isinstance(marker, str) or not 0 < len(marker) <= 4096:
        return False
    try:
        with path.open(errors="replace") as stream:
            tail = ""
            while chunk := stream.read(65536):
                text = tail + chunk
                if marker in text:
                    return True
                tail = text[-max(1, len(marker) - 1):]
    except OSError:
        return False
    return False


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch-file", type=Path, required=True)
    args = parser.parse_args(argv)
    path = args.launch_file
    launch = decode_json(path.read_bytes())
    approved = from_wire(launch["approved"], ApprovedExecutionPlan)
    root = path.parent
    cancelled = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda _s, _f: cancelled.set())
    startup = {"kind": "startup", "schema": "chat-hpc-control/worker-start/v1",
               "site_id": approved.site_id, "run_id": approved.run_id,
               "reservation_id": launch["reservation_id"], "executor_id": launch["executor_id"],
               "manifest_sha256": approved.manifest_sha256, "plan_sha256": digest_file(path),
               "identity": process_identity(os.getpid()), "observed_at": utc_now()}
    write_receipt(root, startup)
    for name in ("stdout.log", "stderr.log"):
        fd = os.open(root / name, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
        os.close(fd)
    program, slot_fd = None, None
    state, reason, exit_code = "FAILED", "WORKER_ERROR", None
    affinity = []
    try:
        for name in ("home", "tmp", "scratch"):
            directory = root / name
            if directory.is_symlink():raise ValueError("linked private worker directory")
            directory.mkdir(mode=0o700, exist_ok=True)
        manifest = validate_approval(approved)
        slot_fd = _slot(Path(launch["queue_root"]), launch["max_concurrent"], cancelled)
        if slot_fd is None:
            state, reason = "CANCELLED", "CANCELLED_BEFORE_START"
        else:
            # A local queue wait can outlive a runtime/environment update.
            manifest = validate_approval(approved)
            work = approved.plan.cwd
            work.mkdir(mode=0o700, parents=True, exist_ok=True)
            for record in manifest["files"]:
                source, target = approved.input_root / record["path"], work / record["path"]
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                if target.is_symlink():
                    raise ValueError("working input must not be a link")
                shutil.copyfile(source, target)
                target.chmod(0o600)
            environment = {"PATH": os.defpath, "HOME": str(root / "home"), "TMPDIR": str(root / "tmp"),
                           "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                           **approved.plan.environment}
            for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
                environment[key] = str(approved.plan.resources.cpus)
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            affinity = sorted(os.sched_getaffinity(0))[:approved.plan.resources.cpus]
            if len(affinity) != approved.plan.resources.cpus:
                raise ValueError("CPU affinity is smaller than the approved request")
            def initial_affinity():
                os.sched_setaffinity(0, affinity)
            with (root / "stdout.log").open("wb") as stdout, (root / "stderr.log").open("wb") as stderr:
                validate_approval(approved)
                program = subprocess.Popen(approved.plan.argv, cwd=work, env=environment,
                                           stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                           close_fds=True, start_new_session=True, preexec_fn=initial_affinity)
                write_receipt(root, {"kind": "program-start", "run_id": approved.run_id,
                                    "identity": process_identity(program.pid), "observed_at": utc_now(),
                                    "initial_affinity": affinity})
                started = time.monotonic()
                while program.poll() is None:
                    if cancelled.is_set():
                        state, reason = "CANCELLED", "EXTERNAL_CANCELLATION"
                        _terminate(program)
                        break
                    walltime = approved.plan.resources.walltime_seconds
                    if walltime is not None and time.monotonic() - started >= walltime:
                        reason = "WALLTIME_EXCEEDED"
                        _terminate(program)
                        break
                    if sum((root / name).stat().st_size for name in ("stdout.log", "stderr.log")) > launch["output_limit"]:
                        reason = "OUTPUT_LIMIT_EXCEEDED"
                        _terminate(program)
                        break
                    time.sleep(.05)
                exit_code = program.wait()
                if reason == "WORKER_ERROR":
                    state = "COMPLETED" if exit_code == 0 else "FAILED"
                    reason = "NORMAL_EXIT" if exit_code == 0 else "NATIVE_EXIT_NONZERO"
                termination = approved.plan.program_identity.get("normal_termination")
                if state == "COMPLETED" and termination:
                    filename = termination["file"]
                    checked_paths([filename])
                    output = root / "stdout.log" if filename == "stdout.log" else work / filename
                    if not _has_marker(output, termination["marker"]):
                        state, reason = "FAILED", "NORMAL_TERMINATION_UNCONFIRMED"
    except Exception:
        _terminate(program)
        state = "FAILED"
        reason = "WORKER_VALIDATION_OR_EXECUTION_ERROR"
        if program is not None:
            exit_code = program.returncode
    finally:
        if slot_fd is not None:
            os.close(slot_fd)
        logs = [{"path": name, "size": (root / name).stat().st_size, "sha256": digest_file(root / name)}
                for name in ("stdout.log", "stderr.log")]
        terminal = {"kind": "terminal", "schema": "chat-hpc-control/worker-terminal/v1",
                    "run_id": approved.run_id, "reservation_id": launch["reservation_id"],
                    "manifest_sha256": approved.manifest_sha256, "plan_sha256": startup["plan_sha256"],
                    "startup_sha256": digest_file(root / "startup.json"), "execution_state": state,
                    "exit_code": exit_code, "reason": reason, "observed_at": utc_now(), "logs": logs,
                    "initial_affinity": affinity, "memory_enforcement": "advisory",
                    "cpu_enforcement": "initial-affinity-and-thread-env",
                    "walltime_seconds": approved.plan.resources.walltime_seconds}
        write_receipt(root, terminal)
    return 0 if state == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
