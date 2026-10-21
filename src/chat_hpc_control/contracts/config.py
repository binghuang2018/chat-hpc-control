"""Private site values, distinct from user-supplied task specifications."""

from dataclasses import dataclass, field
from pathlib import Path
from .task import JsonObject


@dataclass(frozen=True)
class RuntimeConfig:
    executable: str
    version_args: tuple[str, ...] = ("--version",)
    environment: dict[str, str] = field(default_factory=dict)
    mpi_argv: tuple[str, ...] = ()
    options: JsonObject = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutorConfig:
    kind: str
    identity: str
    options: JsonObject = field(default_factory=dict)


@dataclass(frozen=True)
class SiteConfig:
    site_id: str
    root: Path
    principals: dict[str, JsonObject]
    engines: dict[str, RuntimeConfig]
    executor: ExecutorConfig
    repositories: dict[str, str] = field(default_factory=dict)
    limits: dict[str, int] = field(default_factory=dict)
    policy_revision: str = "1"
    gateway_uids: tuple[int, ...] = ()
    local_principals: dict[int, str] = field(default_factory=dict)
    settings: JsonObject = field(default_factory=dict)
