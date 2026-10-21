"""Deterministic identities and append-only frozen input snapshots."""

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from ..contracts.codec import check_json_tree
from ..contracts.config import SiteConfig
from ..contracts.errors import ControlError
from ..contracts.plugins import PluginInfo, ProbeReport
from ..contracts.task import FrozenTask, JsonObject, ResolvedTask
from ..sources.base import check_limits, checked_paths
from ..sources.bundle import file_records, read_verified


def canonical_bytes(value: JsonObject) -> bytes:
    check_json_tree(value, allow_float=False)
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_manifest(task: ResolvedTask, plugin: PluginInfo, probe: ProbeReport, site: SiteConfig) -> JsonObject:
    runtime = site.engines.get(task.task.engine_id)
    runtime_identity = {}
    if runtime:
        runtime_identity = {"executable": runtime.executable, "mpi_argv": list(runtime.mpi_argv),
                            "environment_sha256": hashlib.sha256(canonical_bytes(runtime.environment)).hexdigest()}
    return {
        "schema": "chat-hpc-control/task-manifest/v1",
        "canonicalization": "canonical-json-v1",
        "task": task.task.to_dict(), "files": file_records(task.files),
        "source_identity": task.source_identity,
        "plugin": {"engine_id": plugin.engine_id, "api_version": plugin.api_version,
                   "distribution": plugin.distribution, "version": plugin.version,
                   "code_sha256": plugin.code_sha256},
        "program": {"version": probe.version, "identity": probe.identity, "runtime": runtime_identity},
        "site": {"site_id": site.site_id, "policy_revision": site.policy_revision,
                 "executor": asdict(site.executor), "limits": site.limits},
    }


def freeze(task: ResolvedTask, site: SiteConfig, *, manifest: JsonObject | None = None) -> FrozenTask:
    checked_paths(list(task.files))
    check_limits(task.files, site)
    if manifest is None:
        manifest = {"schema": "chat-hpc-control/input-snapshot/v1", "task": task.task.to_dict(),
                    "files": file_records(task.files), "source_identity": task.source_identity}
    if manifest["files"] != file_records(task.files) or manifest["task"] != task.task.to_dict():
        raise ControlError("INPUT_CHANGED", "manifest does not describe the resolved source")
    raw = canonical_bytes(manifest)
    digest = hashlib.sha256(raw).hexdigest()
    base = site.root / "inputs"
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = base / digest
    if target.exists():
        if target.is_symlink() or (target / "manifest.json").read_bytes() != raw:
            raise ControlError("INPUT_CHANGED", "existing input identity changed")
        read_verified(target / "files", manifest["files"])
    else:
        stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=base))
        try:
            for name, data in task.files.items():
                path = stage / "files" / name
                path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                path.write_bytes(data)
                path.chmod(0o400)
            (stage / "manifest.json").write_bytes(raw)
            (stage / "manifest.json").chmod(0o400)
            os.rename(stage, target)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return FrozenTask(task.task, manifest, digest, target / "files")
