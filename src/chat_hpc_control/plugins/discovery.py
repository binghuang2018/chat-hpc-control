"""Enumerate metadata without importing any plugin implementation."""

from dataclasses import dataclass
import hashlib
import importlib.metadata as metadata
from pathlib import Path
import re

from ..contracts.errors import ControlError
from ..core.manifest import canonical_bytes

GROUP = "chat_hpc_control.engines"


def installed_entries():
    return metadata.entry_points(group=GROUP)


def normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass(frozen=True)
class PluginDescriptor:
    engine_id: str
    distribution: str
    version: str
    entry_point: str
    code_sha256: str


def distribution_digest(distribution) -> str:
    rows = []
    for item in sorted(distribution.files or [], key=str):
        name = str(item)
        if name.endswith((".pyc", ".pyo")) or name.endswith(".dist-info/RECORD"):
            continue
        path = Path(distribution.locate_file(item))
        if not path.is_file() or path.is_symlink():
            raise ControlError("PLUGIN_INCOMPATIBLE", "installed plugin file is unavailable")
        rows.append({"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    if not rows:
        raise ControlError("PLUGIN_INCOMPATIBLE", "distribution has no verifiable file inventory")
    # Editable core installs are supported during development; hash the actual
    # core sources as well as installation metadata. Production wheels list them.
    if normalized(distribution.metadata["Name"]) == "chat-hpc-control":
        base = Path(__file__).resolve().parents[1]
        for path in sorted(base.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                rows.append({"path": "core-source/" + str(path.relative_to(base)),
                             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return hashlib.sha256(canonical_bytes({"files": rows})).hexdigest()


def discover_enabled(site) -> dict[str, PluginDescriptor]:
    found = {}
    allowlist = site.settings.get("plugin_allowlist", {})
    for entry in installed_entries():
        if entry.name not in site.engines:
            continue
        if entry.name in found:
            raise ControlError("PLUGIN_INCOMPATIBLE", "duplicate enabled engine ID")
        distribution = entry.dist
        name = normalized(distribution.metadata["Name"])
        approved = allowlist.get(entry.name, "chat-hpc-control")
        if name != normalized(approved):
            raise ControlError("PLUGIN_INCOMPATIBLE", "engine distribution is not approved")
        found[entry.name] = PluginDescriptor(entry.name, name, distribution.version,
                                            entry.value, distribution_digest(distribution))
    return found
