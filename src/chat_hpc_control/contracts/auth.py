"""Contexts created by authenticated transports, never by task parameters."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CallContext:
    principal: str
    site_id: str
    scopes: frozenset[str]
    transport: str = "local"
    actor: str | None = None
    author: str | None = None


@dataclass(frozen=True)
class PeerIdentity:
    uid: int
    gid: int
    pid: int
