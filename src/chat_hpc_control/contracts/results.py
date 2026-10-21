"""Numerical completeness is not scientific acceptance."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from .auth import CallContext
from .task import JsonObject, ResultContract


@dataclass(frozen=True)
class OutputSnapshot:
    root: Path
    files: list[JsonObject]
    manifest_sha256: str
    terminal: JsonObject


@dataclass(frozen=True)
class ParseReport:
    profile: str
    parser_identity: JsonObject
    records: list[JsonObject] = field(default_factory=list)
    issues: list[JsonObject] = field(default_factory=list)
    supported: bool = True


@dataclass(frozen=True)
class CollectionRef:
    run_id: str
    collection_id: str
    root: Path


@dataclass(frozen=True)
class ResultPage:
    collection_id: str | None
    records: list[JsonObject]
    next_cursor: str | None
    summary: JsonObject


@dataclass(frozen=True)
class RunStatus:
    run_id: str
    execution_state: str
    observed_at: str | None
    collection_state: str = "PENDING"
    publication_state: str = "NOT_REQUESTED"
    evidence: JsonObject = field(default_factory=dict)


@dataclass(frozen=True)
class PublishReceipt:
    collection_id: str
    target: str
    state: str
    identity: JsonObject = field(default_factory=dict)


@dataclass(frozen=True)
class CompatibilityReport:
    records: list[JsonObject]
    issues: list[JsonObject]


class ResultReader(Protocol):
    def get_page(self, run_id: str, collection_id: str | None, fields: list[str],
                 cursor: str | None, page_size: int, context: CallContext) -> ResultPage: ...
    def get_manifest(self, run_id: str, collection_id: str | None,
                     context: CallContext) -> JsonObject: ...
