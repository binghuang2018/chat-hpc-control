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
    engines: frozenset[str] = frozenset()
    repositories: frozenset[str] = frozenset()
    read_all: bool = False


@dataclass(frozen=True)
class PeerIdentity:
    uid: int
    gid: int
    pid: int
