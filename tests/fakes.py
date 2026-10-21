from pathlib import Path

from chat_hpc_control.contracts.execution import (
    ExecutionPlan, ExecutorCapabilities, ExecutorInfo, ReconciliationReport,
    RunHandle, SubmissionReceipt,
)
from chat_hpc_control.contracts.plugins import PluginInfo, ProbeReport, ValidationReport


class DemoEngine:
    def __init__(self):
        self.probe_calls = 0
        self.version = "synthetic-1"
    def info(self):
        return PluginInfo("demo", "test-only-demo", "1", "d" * 64)
    def probe(self, runtime):
        self.probe_calls += 1
        return ProbeReport(True, self.version, {"program_sha256": "a" * 64})
    def validate(self, task, context):
        return ValidationReport(True, task.task)
    def prepare(self, task, context):
        return ExecutionPlan((context.runtime.executable, str(task.input_root / task.task.entrypoint)),
                             context.run_root, {}, ("stdout.log",), task.task.resources, "demo")


class RecordingExecutor:
    def __init__(self):
        self.submissions = []
        self.receipts = {}
        self.lose_response = False
    def info(self):
        return ExecutorInfo("example-local")
    def probe(self, config):
        return ExecutorCapabilities(4, 2048)
    def submit(self, plan, reservation_id):
        self.submissions.append(reservation_id)
        handle = RunHandle(plan.site_id, "example-local", str(len(self.submissions)), str(plan.plan.cwd),
                           {"command_sha256": "c" * 64, "boot_id": "test-boot"})
        receipt = SubmissionReceipt(reservation_id, plan.run_id, "QUEUED", handle)
        self.receipts[reservation_id] = receipt
        if self.lose_response:
            raise ConnectionError("simulated lost native response")
        return receipt
    def reconcile(self, reservation):
        if reservation.reservation_id in self.receipts:
            return ReconciliationReport("SUBMITTED", self.receipts[reservation.reservation_id])
        return ReconciliationReport("NOT_SUBMITTED")
