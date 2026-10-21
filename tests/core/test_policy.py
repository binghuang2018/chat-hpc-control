import importlib
import os

import pytest

from chat_hpc_control.contracts.auth import CallContext, PeerIdentity
from chat_hpc_control.contracts.config import ExecutorConfig, SiteConfig
from chat_hpc_control.contracts.errors import ControlError
from chat_hpc_control.contracts.execution import ExecutorCapabilities
from chat_hpc_control.contracts.task import ResourceRequest


def api(module):
    try:
        return importlib.import_module("chat_hpc_control.core." + module)
    except ModuleNotFoundError:
        pytest.fail("site authorization/resource implementation is missing")


@pytest.fixture
def policy_site(tmp_path):
    return SiteConfig("example-site", tmp_path, {
        "alice": {"scopes": ["tasks:submit", "tasks:read"], "engines": ["demo"], "repositories": []},
        "bob": {"scopes": ["tasks:read"], "engines": [], "repositories": []},
    }, {}, ExecutorConfig("local", "example"), gateway_uids=(1001,), local_principals={1000: "alice"})


def test_actor_spoofing(policy_site):
    with pytest.raises(ControlError, match="AUTH_DENIED"):
        api("auth").context_from_peer(PeerIdentity(1000, 1000, 99),
                                     {"context": {"principal": "bob"}}, policy_site)


def test_gateway_scope_escalation(policy_site):
    with pytest.raises(ControlError, match="AUTH_DENIED"):
        api("auth").context_from_peer(PeerIdentity(1001, 1001, 99),
            {"context": {"principal": "bob", "site_id": "example-site", "transport": "mcp",
                         "scopes": ["tasks:submit"]}}, policy_site)


@pytest.mark.parametrize("field,value", [("principal", {}), ("actor", []), ("scopes", [{}])])
def test_gateway_malformed_identity_is_rejected(policy_site, field, value):
    identity = {"principal": "alice", "site_id": "example-site", "transport": "mcp",
                "scopes": ["tasks:read"]}
    identity[field] = value
    with pytest.raises(ControlError, match="AUTH_DENIED"):
        api("auth").context_from_peer(PeerIdentity(1001, 1001, 99), {"context": identity}, policy_site)


def test_peer_identity_mapping(policy_site):
    ctx = api("auth").context_from_peer(PeerIdentity(1000, 1000, 99), {}, policy_site)
    assert ctx.principal == "alice"
    assert ctx.scopes == frozenset({"tasks:submit", "tasks:read"})
    api("auth").authorize(ctx, "tasks:submit", None)


def test_author_actor_both_required(policy_site):
    peer = PeerIdentity(1001, 1001, 10)
    env = {"context": {"principal": "alice", "site_id": "example-site",
                      "transport": "github", "author": "alice", "actor": "bob",
                      "scopes": ["tasks:submit"]}}
    with pytest.raises(ControlError, match="AUTH_DENIED"):
        api("auth").context_from_peer(peer, env, policy_site)
    env["context"]["actor"] = "alice"
    ctx = api("auth").context_from_peer(peer, env, policy_site)
    assert ctx.author == ctx.principal == "alice"


def test_github_actor_engine_scope_is_not_bypassed(policy_site):
    api("auth")
    policy_site.principals["bob"]["scopes"] = ["tasks:submit"]
    peer = PeerIdentity(1001, 1001, 10)
    ctx = api("auth").context_from_peer(peer, {"context": {
        "principal": "alice", "author": "alice", "actor": "bob",
        "site_id": "example-site", "transport": "github", "scopes": ["tasks:submit"]}}, policy_site)
    from chat_hpc_control.contracts.task import TaskSpec
    task = TaskSpec("demo-1", "demo", {}, {"kind": "bundle", "bundle_id": "x"}, "job.py",
                    ResourceRequest(1, 64, None), None)
    with pytest.raises(ControlError, match="AUTH_DENIED"):
        api("auth").authorize(ctx, "tasks:submit", task)


@pytest.mark.parametrize("owner,site_id", [("bob", "example-site"), ("alice", "other-site")])
def test_cross_site_and_owner(policy_site, owner, site_id):
    ctx = api("auth").context_from_peer(PeerIdentity(1000, 1000, 99), {}, policy_site)
    with pytest.raises(ControlError, match="AUTH_DENIED"):
        api("auth").authorize_run(ctx, owner, site_id, "tasks:read")


def test_unlimited_resources():
    fn = api("resources").validate_resources
    request = ResourceRequest(2, 512, None)
    assert fn(request, ExecutorCapabilities(4, 1024)).walltime_seconds is None
    with pytest.raises(ControlError, match="RESOURCE_UNSUPPORTED"):
        fn(request, ExecutorCapabilities(4, 1024, accepts_unlimited_walltime=False, max_walltime_seconds=90))


@pytest.mark.parametrize("req", [ResourceRequest(8, 512, None), ResourceRequest(1, 2048, None),
                                ResourceRequest(True, 512, None), ResourceRequest(1, 512, 0)])
def test_resource_limits_are_not_silently_clamped(req):
    with pytest.raises(ControlError, match="RESOURCE_UNSUPPORTED"):
        api("resources").validate_resources(req, ExecutorCapabilities(4, 1024))
