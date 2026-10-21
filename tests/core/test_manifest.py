import importlib
import json

import pytest

from chat_hpc_control.contracts.codec import parse_task
from chat_hpc_control.contracts.config import ExecutorConfig, SiteConfig
from chat_hpc_control.contracts.errors import ControlError
from chat_hpc_control.contracts.plugins import PluginInfo, ProbeReport
from chat_hpc_control.contracts.task import ResolvedTask


def api():
    try:
        return importlib.import_module("chat_hpc_control.core.manifest")
    except ModuleNotFoundError:
        pytest.fail("manifest implementation is missing")


def test_canonical_bytes():
    assert api().canonical_bytes({"中": 1, "a": 2}) == '{"a":2,"中":1}'.encode()


@pytest.mark.parametrize("value", [1.0, float("inf"), 2**53, "\ud800"])
def test_canonical_rejects_unsafe_values(value):
    with pytest.raises(ControlError, match="SCHEMA_INVALID"):
        api().canonical_bytes({"v": value})


def test_manifest_stability(sample_task, tmp_path):
    m = api()
    resolved = ResolvedTask(parse_task(json.dumps(sample_task).encode()), {"job.py": b"print(1)\n"},
                            {"kind": "bundle", "bundle_id": "synthetic"})
    site = SiteConfig("example-site", tmp_path / "site", {}, {}, ExecutorConfig("local", "local-1"))
    plugin = PluginInfo("pyscf", "example-engine", "1", "a" * 64)
    probe = ProbeReport(True, "1", {"program_sha256": "b" * 64})
    first = m.build_manifest(resolved, plugin, probe, site)
    assert first == m.build_manifest(resolved, plugin, probe, site)
    assert first["files"][0]["size"] == 9
    changed_probe = ProbeReport(True, "2", {"program_sha256": "b" * 64})
    assert first != m.build_manifest(resolved, plugin, changed_probe, site)
    changed = ResolvedTask(resolved.task, {"job.py": b"print(2)\n"}, resolved.source_identity)
    assert first != m.build_manifest(changed, plugin, probe, site)
    updated_site = SiteConfig("example-site", site.root, {}, {}, site.executor, policy_revision="2")
    assert first != m.build_manifest(resolved, plugin, probe, updated_site)
    frozen = m.freeze(resolved, site, manifest=first)
    assert (frozen.input_root / "job.py").read_bytes() == b"print(1)\n"
    assert m.freeze(resolved, site, manifest=first).manifest_sha256 == frozen.manifest_sha256
    (frozen.input_root / "job.py").chmod(0o600)
    (frozen.input_root / "job.py").write_bytes(b"tampered")
    with pytest.raises(ControlError, match="INPUT_CHANGED"):
        m.freeze(resolved, site, manifest=first)


def test_control_runtime_upgrade_changes_execution_identity(sample_task, tmp_path, monkeypatch):
    m = api()
    assert hasattr(m, "execution_identity"), "worker/control code is not bound to the manifest"
    task = ResolvedTask(parse_task(json.dumps(sample_task).encode()), {"job.py": b"print(1)\n"}, {"kind": "bundle"})
    site = SiteConfig("example-site", tmp_path / "site", {}, {}, ExecutorConfig("local", "local-1"))
    plugin = PluginInfo("pyscf", "example-engine", "1", "a" * 64)
    probe = ProbeReport(True, "1", {"program_sha256": "b" * 64})
    monkeypatch.setattr(m, "execution_identity", lambda: {"version": "0.1.0", "code_sha256": "a" * 64})
    old = m.build_manifest(task, plugin, probe, site)
    monkeypatch.setattr(m, "execution_identity", lambda: {"version": "0.1.0", "code_sha256": "b" * 64})
    new = m.build_manifest(task, plugin, probe, site)
    assert old != new
