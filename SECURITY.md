# Security and trust model

Version 0.1 is a local candidate, without a public support or disclosure endpoint.
Report issues privately to the site administrator/maintainer through an existing
trusted channel. Do not include credentials or private scientific inputs.

The broker executes administrator-allowlisted **trusted code**. In particular,
PySCF Python and native inputs are not sandboxed against a malicious authorized
principal. Use separate OS accounts/containers/VMs and external cgroups where
required. Native CPU affinity is initial; memory is advisory; null walltime means
no framework calculation deadline, not immunity from host termination.

Keep broker state, source mirrors, runtime binaries and gateway UIDs private.
Models cannot grant identity, add paths, change installed runtimes or authorize
new calculation intents. Gateway credentials stay outside the worker. Direct
Gemini mode disables ambient Vertex selection. No SDK client is created by core
imports. Source and output symlinks, special files and oversize data are rejected.

Do not expose the Unix socket or loopback MCP HTTP directly to the Internet. MCP
bearer transport is not an OAuth authorization server. See the deployment guide
for request isolation and the compatibility table for untested product clients.

Output text is untrusted data. Parsing and numerical completeness are distinct
from scientific acceptance, which defaults to NOT_EVALUATED. Hashes prove identity,
not the correctness or harmlessness of native programs.
