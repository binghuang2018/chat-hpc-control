"""Execution identity and evidence; a queue number alone is insufficient."""

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from .task import JsonObject, ResourceRequest, TaskSpec


class ExecutionState(StrEnum):
    RESERVED = "RESERVED"
    SUBMISSION_UNKNOWN = "SUBMISSION_UNKNOWN"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ExecutionPlan:
    argv: tuple[str, ...]
    cwd: Path
    environment: dict[str, str]
    outputs: tuple[str, ...]
    resources: ResourceRequest
    engine_id: str
    program_identity: JsonObject = field(default_factory=dict)


@dataclass(frozen=True)
class ApprovedExecutionPlan:
    plan: ExecutionPlan
    site_id: str
    run_id: str
    manifest_sha256: str
    input_root: Path


@dataclass(frozen=True)
class ExecutorInfo:
    executor_id: str
    api_version: str = "1.0"


@dataclass(frozen=True)
class ExecutorCapabilities:
    max_cpus: int
    max_memory_mib: int
    accepts_unlimited_walltime: bool = True
    max_walltime_seconds: int | None = None
    cpu_enforcement: str = "advisory"
    memory_enforcement: str = "advisory"
    restart_recovery: bool = True


@dataclass(frozen=True)
class SubmissionRequest:
    site_id: str
    task: TaskSpec
    expected_manifest_sha256: str
    idempotency_key: str
    rerun_of: str | None = None


@dataclass(frozen=True)
class RunHandle:
    site_id: str
    executor_id: str
    job_id: str
    run_root: str
    identity: JsonObject = field(default_factory=dict)


@dataclass(frozen=True)
class SubmissionReceipt:
    reservation_id: str
    run_id: str
    execution_state: str
    handle: RunHandle | None = None
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    run_id: str
    site_id: str
    owner: str
    idempotency_key: str
    fingerprint: str
    request: JsonObject
    execution_state: str = "RESERVED"


@dataclass(frozen=True)
class ExecutionObservation:
    execution_state: str
    identity_verified: bool
    observed_at: str
    exit_code: int | None = None
    evidence: JsonObject = field(default_factory=dict)


@dataclass(frozen=True)
class ReconciliationReport:
    outcome: str
    receipt: SubmissionReceipt | None = None
    evidence_refs: tuple[str, ...] = ()
