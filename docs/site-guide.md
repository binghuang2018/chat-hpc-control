# Site operator guide

Native execution supports **Linux x86_64**. Python 3.11–3.13 is required. Core/client
and schema operations also support macOS. Use a dedicated short private local
filesystem root; broker state rejects known network filesystems and foreign SQLite
databases. One broker writer owns the state lock for its entire lifetime.

## Explicit configuration

`examples/site.demo.toml.in` is the complete synthetic template. Resolve every
placeholder (`ROOT`, absolute `PYTHON`, OS `UID`, CPU capacity); no production
account/path/default node is built in. Required sections are principals, enabled
engines, executor, repositories, input/output budgets, local UID mapping and
settings. The demo command fills these values for its isolated site only.

Start a broker with an explicit configuration:

```sh
chat-hpc-control --site /example/private/site.toml broker serve
```

The private socket is `0600`; Unix kernel peer credentials establish local caller
identity. Trusted gateway UIDs may forward separately authenticated GitHub/MCP
contexts. Mapping a UID is not filesystem permission: cross-account deployments
must separately provision narrow socket/directory ACLs or a private authenticated
bridge. Do not broaden the runtime root to world-readable/writable permissions.

Principals declare exact scopes, engines and source repositories. Read ownership
is enforced; `read_all` is explicit. Publication additionally needs
`results:publish` and an allowlisted target, outside the six chat tools. GitHub
Issue author and actor must both be permitted, with capability intersection.

## Engines and runtime identity

Enable only actually installed administrator-chosen absolute executables. A native
version probe/identity failure rejects submission, with no binary/version fallback.
Runtime `version_args`, environment and `mpi_argv` are private fixed configuration;
models cannot inject `module load` or shell commands. Resolve modules to an
explicit environment before configuration. Keep license files outside inputs and
publication; never put API/private control credentials in a runtime environment.

- `pyscf`: configure the Python containing PySCF; it runs a frozen native script
  with `-B`. Script metadata is labeled script-reported.
- `orca`: configure the ORCA executable and required MPI environment. Native PAL/
  memory directives must match your requested resources; this framework does not
  rewrite scientific input or prove MPI binding. Numerical profiles are limited.
- `molpro`: configure the licensed launcher and fixed MPI/environment policy.
  `-n` follows requested CPUs; any outer MPI configuration requires separate site
  validation. v0.1 has no real Molpro/MPI deployment guarantee.

Runtime manifests record configured executables, versions, environment identity,
control/plugin code and interpreter/dependency identity. Preserve the installed
runtime for queued/running jobs; changing it cannot silently execute a frozen task
under a different identity. Keep original runtime provenance for old results.

## Resources and queues

CPU and memory requests are mandatory. Initial affinity and thread environment are
observed; they do not reserve exclusive cores. Memory is **advisory**, not a hard
cgroup allocation. Queue slots/concurrency do not establish kernel isolation.
Use an external scheduler/supervisor/resource boundary when hard guarantees matter.

`walltime_seconds: null` has no framework calculation deadline. A positive value
terminates the native process group at that explicitly requested limit. If an
operator sets `max_walltime_seconds`, unlimited requests are rejected rather than
clamped. Plugin/RPC/client control waits do not become calculation timeouts.
Input/output byte/file budgets are explicit. Snapshot limits are not disk quotas.

For Task Spooler set `kind="task-spooler"`, an absolute `executable`, a dedicated
short `socket_path` inside the site root and capacity options. The instance binds
socket inode, server boot/PID/start identity and binary; jobs bind full command,
reservation and immutable scheduler receipts. Unknown sockets are not adopted.
Reads cannot start a replacement server. Never reuse an old/shared `TS_SOCKET`,
clear another queue, or assume a reused numeric job ID belongs to an old run.
Queue loss leaves uncertain live jobs unverified; historical terminal receipts can
still prove completed work. Re-establishing a lost instance is an operator action.

## Lifecycle and services

Detached workers survive the submitting client/broker process. They cannot survive
a machine loss or an external cgroup/supervisor that kills them. The example unit
uses `KillMode=process`; review it for your deployment and test a real restart
before claiming service-level survival. The supplied unit is **an uninstalled,
unverified deployment template**. It was not installed on a production node.

Root-owned service/user/ACL setup belongs to an operator. No automatic privileged
installer is included. Drain or isolate old runtimes before upgrades; preserve
state, frozen inputs, run receipts and collections. Unknown submissions must be
reconciled with their original key, never blindly resubmitted.

## Credential and trust boundary

Native Python/QC inputs and plugins are trusted code. Same-UID environment
filtering does not protect secrets from hostile code reading the filesystem or
`/proc`. Keep real model/GitHub credentials on a separate control gateway and
provision the necessary user/container/host boundary. v0.1 is not an anonymous
multi-tenant service. The synthetic local demo needs no credential at all.

See [MCP](mcp-deployment.md), [client intents](client-intents.md),
[publication](publication-guide.md) and [compatibility](compatibility.md) for the
verified scope of each integration.
