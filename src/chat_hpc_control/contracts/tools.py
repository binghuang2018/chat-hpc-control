"""Provider-neutral tools; authentication is outside arguments."""

from dataclasses import asdict, dataclass
from .task import JsonObject


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: JsonObject
    provider_call_id: str | None = None


@dataclass(frozen=True)
class ToolResponse:
    request_id: str
    ok: bool
    data: JsonObject | None = None
    error: JsonObject | None = None
    schema: str = "chat-hpc-control/tool-response/v1"

    def to_dict(self) -> JsonObject:
        return asdict(self)
