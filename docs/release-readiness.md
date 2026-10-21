# Local v0.1 release readiness

The owner approved the architecture, all implementation plans and Native execution.
Newly authored code and synthetic fixtures use **Apache-2.0**. This is a local
candidate; external repository/package naming, public visibility and actual
publication require a separate owner decision.

## Implemented scope

- Installable core/CLI and strict versioned protocols, without mandatory model SDKs.
- Frozen source/runtime identity, authenticated single-writer broker and durable intent.
- Linux x86_64 local/private Task Spooler execution and independent demo plugin.
- PySCF/ORCA/Molpro native input interfaces with explicitly bounded parser profiles.
- Declared numerical completeness, immutable results, pagination and publication receipts.
- Authenticated GitHub/MCP gateways and optional OpenAI/Anthropic/Gemini clients.
- Read-only legacy identity inspection; no adoption or migration of active legacy work.
- English/Chinese quickstarts, plugin/site/result guides, locked dependencies and CI.

## Release gate

The authoritative evidence matrix, independent review and remaining gaps are in
[v0.1 acceptance](v0.1-acceptance.md). The local artifact directory contains wheel,
sdist, demo wheel, SHA256SUMS and a machine-readable release manifest. The manifest
records source commit, dirty status, package/protocol versions and captured evidence.
An absent command/log/version/result cannot be converted to PASS.

CI uses GitHub-hosted runners and full official Action commit references. It has
not been run on GitHub for this candidate. The manual candidate workflow builds
and retains an Artifact only; it cannot publish to PyPI or alter a deployed site.

## Separate external gate

Not performed: public remote creation, pushes, release tags, PyPI/Action publishing,
real GitHub Issues/Artifacts, real model calls, commercial QC validation, production
service installation, and node migration. No existing node was connected or modified.

A publishable control package does not certify arbitrary scientific inputs or
physical conclusions. `data_ready` describes the declared numerical contract;
scientific acceptance defaults to `NOT_EVALUATED`.
