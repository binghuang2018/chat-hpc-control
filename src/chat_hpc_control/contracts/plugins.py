"""Engine and executor API v1.0 structural protocols."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from .config import ExecutorConfig, RuntimeConfig, SiteConfig
from .execution import (ApprovedExecutionPlan, ExecutionObservation, ExecutionPlan,
                        ExecutorCapabilities, ExecutorInfo, ReconciliationReport,
                        Reservation, RunHandle, SubmissionReceipt)
from .results import OutputSnapshot, ParseReport
from .task import FrozenTask, JsonObject, ResolvedTask, ResultContract, TaskSpec


@dataclass(frozen=True)
class PluginInfo:
    engine_id: str
    distribution: str
    version: str
    code_sha256: str
    profiles: tuple[str, ...] = ("raw-only",)
    options_schema: JsonObject = field(default_factory=lambda: {"type": "object", "additionalProperties": False})
    api_version: str = "1.0"


@dataclass(frozen=True)
class ProbeReport:
    available: bool
    version: str
    identity: JsonObject
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationContext:
    site: SiteConfig


@dataclass(frozen=True)
class PrepareContext:
    site: SiteConfig
    run_root: Path
    runtime: RuntimeConfig


@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    task: TaskSpec | None = None
    manifest_sha256: str | None = None
    manifest: JsonObject | None = None
    issues: tuple[str, ...] = ()


class EnginePlugin(Protocol):
    def info(self) -> PluginInfo: ...
    def probe(self, site_runtime: RuntimeConfig) -> ProbeReport: ...
    def validate(self, task: ResolvedTask, context: ValidationContext) -> ValidationReport: ...
    def prepare(self, task: FrozenTask, context: PrepareContext) -> ExecutionPlan: ...
    def parse(self, snapshot: OutputSnapshot, contract: ResultContract) -> ParseReport: ...


class ExecutorPlugin(Protocol):
    def info(self) -> ExecutorInfo: ...
    def probe(self, site: ExecutorConfig) -> ExecutorCapabilities: ...
    def submit(self, plan: ApprovedExecutionPlan, reservation_id: str) -> SubmissionReceipt: ...
    def query(self, handle: RunHandle) -> ExecutionObservation: ...
    def reconcile(self, reservation: Reservation) -> ReconciliationReport: ...
