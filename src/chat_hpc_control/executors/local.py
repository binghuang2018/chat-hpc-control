"""Linux local execution with durable receipts and an independent worker."""

import os
from pathlib import Path
import platform
import sys

from ..contracts.errors import ControlError
from ..contracts.execution import ExecutorCapabilities, ExecutorInfo, ExecutionObservation, ReconciliationReport
from ..core.store import utc_now
from ..worker.launcher import launch, receipt_from_start
from ..worker.receipt import verify_process


class LocalExecutor:
    def __init__(self, site):
        self.site = site
        if sys.platform != "linux" or platform.machine() != "x86_64":
            raise ControlError("CAPABILITY_UNSUPPORTED", "v0.1 native execution requires Linux x86_64")

    def info(self):
        return ExecutorInfo(self.site.executor.identity)

    def probe(self, config):
        return ExecutorCapabilities(min(config.options["max_cpus"], len(os.sched_getaffinity(0))),
                                    config.options["max_memory_mib"],
                                    accepts_unlimited_walltime=config.options.get("max_walltime_seconds") is None,
                                    max_walltime_seconds=config.options.get("max_walltime_seconds"),
                                    cpu_enforcement="initial-affinity-and-thread-env",
                                    memory_enforcement="advisory")

    def submit(self, plan, reservation_id):
        return launch(plan, reservation_id, executor_id=self.info().executor_id,
                      queue_root=self.site.root / "local-queue",
                      max_concurrent=self.site.executor.options.get("max_concurrent", 1),
                      output_limit=self.site.limits.get("max_output_bytes", 268435456))

    def query(self, handle):
        root = Path(handle.run_root)
        if (handle.site_id != self.site.site_id or handle.executor_id != self.info().executor_id
                or root.parent != self.site.root / "runs" or root.is_symlink()):
            return ExecutionObservation("UNKNOWN", False, utc_now(), evidence={"reason": "HANDLE_SCOPE_MISMATCH"})
        return verify_process(handle)

    def reconcile(self, reservation):
        root = self.site.root / "runs" / reservation.run_id
        if (root / "startup.json").is_file():
            try:
                receipt = receipt_from_start(root / "approved-plan.json")
                if receipt.reservation_id != reservation.reservation_id:
                    return ReconciliationReport("UNKNOWN")
                return ReconciliationReport("SUBMITTED", receipt)
            except (OSError, ValueError, KeyError):
                return ReconciliationReport("UNKNOWN")
        if (root / "approved-plan.json").exists():
            return ReconciliationReport("UNKNOWN")
        return ReconciliationReport("NOT_SUBMITTED")
