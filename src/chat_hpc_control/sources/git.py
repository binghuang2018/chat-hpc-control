"""Read configured local mirrors only; fetching belongs to a gateway."""

import os
from pathlib import Path
import re
import subprocess

from ..contracts.errors import ControlError
from .base import checked_paths


class GitCliReader:
    def __init__(self, repositories: dict[str, str], *, max_bytes: int = 64 * 1024 * 1024):
        self.repositories = repositories
        self.max_bytes = max_bytes

    def _git(self, repository: str, *argv: str) -> bytes:
        if repository not in self.repositories:
            raise ControlError("SOURCE_NOT_ALLOWED", "unapproved Git repository")
        root = Path(self.repositories[repository])
        if not root.is_absolute() or not root.is_dir():
            raise ControlError("SOURCE_NOT_ALLOWED", "configured mirror is not available")
        env = {"PATH": os.defpath + ":/opt/homebrew/bin", "GIT_CONFIG_NOSYSTEM": "1",
               "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0"}
        try:
            return subprocess.run(["git", "--no-optional-locks", "-c", "core.hooksPath=" + os.devnull,
                                   "-C", str(root), *argv], env=env, check=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30).stdout
        except (subprocess.SubprocessError, OSError) as exc:
            raise ControlError("SOURCE_NOT_ALLOWED", "fixed Git object could not be read") from exc

    def resolve_ref(self, repository: str, ref: str) -> str:
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,255}", ref)
                or ".." in ref or "//" in ref or ref.endswith("/")):
            raise ControlError("SCHEMA_INVALID", "invalid Git reference")
        commit = self._git(repository, "rev-parse", "--verify", ref + "^{commit}").decode().strip()
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
            raise ControlError("INPUT_CHANGED", "not a full Git commit identity")
        return commit

    def read_blob(self, repository: str, commit: str, path: str) -> tuple[str, bytes]:
        checked_paths([path])
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
            raise ControlError("SCHEMA_INVALID", "read requires a full commit")
        entry = self._git(repository, "ls-tree", "-z", commit, "--", path)
        try:
            header, actual_path = entry.rstrip(b"\x00").split(b"\t", 1)
            mode, kind, blob = header.decode().split()
        except ValueError as exc:
            raise ControlError("SCHEMA_INVALID", "missing or ambiguous Git file") from exc
        if mode not in {"100644", "100755"} or kind != "blob" or actual_path.decode() != path:
            raise ControlError("SCHEMA_INVALID", "only regular Git files are accepted")
        size = int(self._git(repository, "cat-file", "-s", blob).strip())
        if size > self.max_bytes:
            raise ControlError("SCHEMA_INVALID", "Git blob exceeds configured input limit")
        return blob, self._git(repository, "cat-file", "blob", blob)
