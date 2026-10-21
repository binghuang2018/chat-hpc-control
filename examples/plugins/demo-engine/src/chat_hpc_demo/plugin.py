"""A transparent synthetic plugin, not a quantum chemistry program."""

import hashlib
import json
from pathlib import Path
import subprocess

from chat_hpc_control.contracts.execution import ExecutionPlan
from chat_hpc_control.contracts.plugins import PluginInfo, ProbeReport, ValidationReport
from chat_hpc_control.contracts.results import ParseReport


class DemoEngine:
    def info(self):
        return PluginInfo("demo", "chat-hpc-demo-engine", "0.1.0", "0" * 64,
                          profiles=("demo-json-v1", "raw-only"))

    def probe(self, site_runtime):
        try:
            result = subprocess.run([site_runtime.executable, *site_runtime.version_args],
                                    capture_output=True, check=True, timeout=10)
            version = (result.stdout + result.stderr).decode(errors="replace").strip()
            digest = hashlib.sha256(Path(site_runtime.executable).resolve().read_bytes()).hexdigest()
            return ProbeReport(True, version, {"program_sha256": digest, "synthetic_engine": True})
        except (OSError, subprocess.SubprocessError):
            return ProbeReport(False, "unavailable", {}, ("synthetic interpreter unavailable",))

    def validate(self, task, context):
        return ValidationReport(task.task.entrypoint in task.files, task.task)

    def prepare(self, task, context):
        return ExecutionPlan((context.runtime.executable, "-B", str(task.input_root / task.task.entrypoint)),
                             context.run_root / "work", context.runtime.environment, ("records.json",),
                             task.task.resources, "demo", {"synthetic_engine": True})

    def parse(self, snapshot, contract):
        try:
            data = json.loads((snapshot.root / "records.json").read_text())
            records = data["records"]
            for record in records:
                record["evidence_level"] = "synthetic"
            return ParseReport("demo-json-v1", {"version": "1", "synthetic": True}, records)
        except (OSError, ValueError, KeyError, TypeError):
            return ParseReport("demo-json-v1", {"version": "1"}, issues=[
                {"code": "UNREADABLE_SYNTHETIC_RESULT"}], supported=False)


def create_plugin():
    return DemoEngine()
