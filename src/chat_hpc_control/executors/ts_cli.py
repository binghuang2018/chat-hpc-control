"""Bounded argv-only Task Spooler control on one explicit private socket."""

import os
from pathlib import Path
import re
import socket
import stat
import subprocess

from ..contracts.errors import ControlError


class TsCli:
    def __init__(self, executable: Path, allowed_root: Path):
        self.executable, self.allowed_root = executable, allowed_root

    def run(self, argv: list[str], socket_path: Path) -> bytes:
        if (not socket_path.is_absolute() or not socket_path.is_relative_to(self.allowed_root)
                or socket_path.is_symlink() or socket_path.resolve().parent != socket_path.parent
                or any(ord(c) < 32 for c in str(socket_path))):
            raise ControlError("SCHEMA_INVALID", "invalid private Task Spooler socket")
        simple = argv in (["-V"], ["-h"], ["-l"], ["-K"])
        indexed = len(argv) == 2 and argv[0] in {"-i", "-s", "-S"} and re.fullmatch(r"[0-9]+", argv[1])
        enqueue = (len(argv) == 11 and argv[0] == "-N" and re.fullmatch(r"[1-9][0-9]*", argv[1])
                   and argv[2] == "-L" and re.fullmatch(r"chc-[0-9a-f-]{36}", argv[3])
                   and Path(argv[4]).is_absolute() and argv[5:10] == ["-I", "-B", "-m", "chat_hpc_control.worker.main", "--launch-file"]
                   and Path(argv[10]).is_absolute())
        if not (simple or indexed or enqueue):
            raise ControlError("SCHEMA_INVALID", "unsupported Task Spooler operation")
        if argv[0] not in {"-V", "-h", "-S"}:
            if not socket_path.exists() or not stat.S_ISSOCK(socket_path.stat().st_mode):
                raise ControlError("JOB_IDENTITY_UNVERIFIED", "configured queue socket is unavailable")
        if argv[0] == "-S" and len(os.fsencode(socket_path)) > 100:
            raise ControlError("SCHEMA_INVALID", "Unix socket path is too long; use a shorter site root")
        private = self.allowed_root / "ts-control"
        private.mkdir(mode=0o700, parents=True, exist_ok=True)
        environment = {"PATH": os.defpath, "HOME": str(private), "TMPDIR": str(private),
                       "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TS_SOCKET": str(socket_path),
                       "TS_MAXFINISHED": "10000", "TS_MAXCONN": "10000"}
        try:
            result = subprocess.run([str(self.executable), *argv], env=environment, cwd=private,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    timeout=15, close_fds=True)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ControlError("JOB_IDENTITY_UNVERIFIED", "Task Spooler control response unavailable") from exc
        if result.returncode or len(result.stdout) > 8 * 1024 * 1024:
            raise ControlError("JOB_IDENTITY_UNVERIFIED", "Task Spooler control response rejected")
        return result.stdout
