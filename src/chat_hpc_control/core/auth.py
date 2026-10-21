"""Trust peer-authenticated transports, not model-supplied identity fields."""

from dataclasses import replace

from ..contracts.auth import CallContext, PeerIdentity
from ..contracts.config import SiteConfig
from ..contracts.errors import ControlError
from ..contracts.task import JsonObject, TaskSpec


def _deny():
    raise ControlError("AUTH_DENIED", "identity, scope, or object ownership is not authorized")


def _context(principal: str, site: SiteConfig, scopes=None, transport="local", actor=None, author=None):
    policy = site.principals.get(principal)
    if not policy:
        _deny()
    allowed = frozenset(policy["scopes"])
    granted = allowed if scopes is None else frozenset(scopes)
    if not granted <= allowed:
        _deny()
    return CallContext(principal, site.site_id, granted, transport, actor, author,
                       frozenset(policy.get("engines", [])),
                       frozenset(policy.get("repositories", [])), bool(policy.get("read_all", False)))


def context_from_peer(peer: PeerIdentity, envelope: JsonObject, site: SiteConfig) -> CallContext:
    if "context" not in envelope:
        principal = site.local_principals.get(peer.uid)
        if not principal:
            _deny()
        return _context(principal, site)
    if peer.uid not in site.gateway_uids:
        _deny()
    identity = envelope["context"]
    keys = {"principal", "site_id", "transport", "scopes", "actor", "author"}
    if (not isinstance(identity, dict) or set(identity) - keys
            or identity.get("site_id") != site.site_id
            or identity.get("transport") not in {"github", "mcp"}
            or not isinstance(identity.get("principal"), str)
            or any(k in identity and not isinstance(identity[k], str) for k in ("actor", "author"))):
        _deny()
    requested = identity.get("scopes")
    if not isinstance(requested, list) or not all(isinstance(s, str) for s in requested):
        _deny()
    if identity["transport"] == "github":
        if identity.get("author") != identity.get("principal") or not identity.get("actor"):
            _deny()
        for person in (identity["author"], identity["actor"]):
            if person not in site.principals or not set(requested) <= set(site.principals[person]["scopes"]):
                _deny()
    result = _context(identity.get("principal"), site, requested, identity["transport"],
                      identity.get("actor"), identity.get("author"))
    if result.transport == "github":
        actor_context = _context(result.actor, site, requested, "github")
        def intersection(a, b):
            return b if "*" in a else a if "*" in b else a & b
        result = replace(result, engines=intersection(result.engines, actor_context.engines),
                         repositories=intersection(result.repositories, actor_context.repositories),
                         read_all=result.read_all and actor_context.read_all)
    return result


def authorize(context: CallContext, action: str, task: TaskSpec | None) -> None:
    if action not in context.scopes:
        _deny()
    if task is not None:
        if task.engine_id not in context.engines and "*" not in context.engines:
            _deny()
        if task.source["kind"] == "git":
            repo = task.source["repository"]
            if repo not in context.repositories and "*" not in context.repositories:
                _deny()


def authorize_run(context: CallContext, owner: str, site_id: str, action: str) -> None:
    authorize(context, action, None)
    if context.site_id != site_id or (context.principal != owner and not context.read_all):
        _deny()
