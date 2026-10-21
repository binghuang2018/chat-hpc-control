"""Native task and immutable source identities."""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

JsonObject = dict[str, Any]
ResultContract = JsonObject


@dataclass(frozen=True)
class ResourceRequest:
    cpus: int
    memory_mib: int
    walltime_seconds: int | None


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    engine_id: str
    engine_options: JsonObject
    source: JsonObject
    entrypoint: str
    resources: ResourceRequest
    expected_results: ResultContract | None
    schema: str = "chat-hpc-control/task/v1"

    def to_dict(self) -> JsonObject:
        return asdict(self)


@dataclass(frozen=True)
class ResolvedTask:
    task: TaskSpec
    files: dict[str, bytes]
    source_identity: JsonObject


@dataclass(frozen=True)
class FrozenTask:
    task: TaskSpec
    manifest: JsonObject
    manifest_sha256: str
    input_root: Path


@dataclass(frozen=True)
class TaskRef:
    site_id: str
    task_id: str
    manifest_sha256: str
