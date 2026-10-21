"""Source resolution fixes one commit and verifies every Git blob."""

import hashlib
from pathlib import PurePosixPath
import unicodedata

from ..contracts.config import SiteConfig
from ..contracts.errors import ControlError
from ..contracts.task import ResolvedTask, TaskSpec


def checked_paths(paths: list[str]) -> list[str]:
    seen = set()
    for name in paths:
        if not isinstance(name, str) or not name or "\x00" in name or "\\" in name:
            raise ControlError("SCHEMA_INVALID", "invalid input path")
        parts = name.split("/")
        if (name.startswith("/") or len(name.encode("utf-8")) > 4096
                or any(p in {"", ".", ".."} for p in parts) or len(parts) > 256
                or PurePosixPath(name).is_absolute()):
            raise ControlError("SCHEMA_INVALID", "input path escapes or is ambiguous")
        normalized = unicodedata.normalize("NFC", name)
        if normalized in seen:
            raise ControlError("SCHEMA_INVALID", "duplicate or Unicode-equivalent path")
        seen.add(normalized)
    names = sorted(paths)
    for i, name in enumerate(names):
        if i and name.startswith(names[i - 1] + "/"):
            raise ControlError("SCHEMA_INVALID", "file path conflicts with directory")
    return names


def check_limits(files: dict[str, bytes], site: SiteConfig):
    if (len(files) > site.limits.get("max_input_files", 1024)
            or sum(map(len, files.values())) > site.limits.get("max_input_bytes", 64 * 1024 * 1024)):
        raise ControlError("SCHEMA_INVALID", "input bundle exceeds configured limits")


class SourceResolver:
    def __init__(self, git_reader=None):
        self.git_reader = git_reader

    def resolve(self, task: TaskSpec, site: SiteConfig) -> ResolvedTask:
        if task.source["kind"] == "bundle":
            from .bundle import BundleStore
            bundle_id = task.source["bundle_id"]
            data = BundleStore(site).read(bundle_id)
            identity = {"kind": "bundle", "bundle_id": bundle_id}
            pinned = task
        else:
            from .git import GitCliReader
            repository = task.source["repository"]
            if repository not in site.repositories:
                raise ControlError("SOURCE_NOT_ALLOWED", "repository is not approved")
            from .staged_git import StagedGitReader
            reader = self.git_reader or StagedGitReader(site, GitCliReader(
                site.repositories, max_bytes=site.limits.get("max_input_bytes", 64 * 1024 * 1024)))
            commit = reader.resolve_ref(repository, task.source["ref"])
            names = checked_paths(task.source["files"])
            data, blobs = {}, {}
            for path in names:
                blob, content = reader.read_blob(repository, commit, path)
                header = f"blob {len(content)}\x00".encode() + content
                expected = hashlib.sha1(header).hexdigest() if len(blob) == 40 else hashlib.sha256(header).hexdigest()
                if blob != expected:
                    raise ControlError("INPUT_CHANGED", "Git blob content does not match its identity")
                data[path] = content
                blobs[path] = blob
            from ..contracts.codec import parse_task
            import json
            obj = task.to_dict()
            obj["source"]["ref"] = commit
            pinned = parse_task(json.dumps(obj).encode())
            identity = {"kind": "git", "repository": repository, "commit": commit, "blobs": blobs}
        checked_paths(list(data))
        check_limits(data, site)
        if task.entrypoint not in data:
            raise ControlError("SCHEMA_INVALID", "entrypoint is not in frozen files")
        if task.expected_results:
            for record in task.expected_results["records"]:
                if record["geometry_file"] not in data:
                    raise ControlError("SCHEMA_INVALID", "declared geometry is not in frozen files")
        return ResolvedTask(pinned, data, identity)
