# chat-hpc-control

A provider-neutral control plane for reproducible native quantum-chemistry jobs.
v0.1 provides a local broker, durable workers, extensible engine/executor plugins,
declaration-driven results, and optional GitHub, MCP and model-client adapters.

**Local release candidate.** No public package/repository name is reserved by this
checkout. Existing production deployments are outside this project and unchanged.

## Start here

- [Linux synthetic quickstart](docs/quickstart.md) · [中文入门](docs/quickstart.zh-CN.md)
- [Site configuration](docs/site-guide.md) · [Plugin developer guide](docs/plugin-guide.md)
- [Results and numerical checks](docs/results-guide.md) · [Publication](docs/publication-guide.md)
- [Compatibility and evidence](docs/compatibility.md) · [Release acceptance](docs/v0.1-acceptance.md)

## What v0.1 does

| Component | Scope |
| --- | --- |
| Engines | Native PySCF Python, ORCA input, Molpro input; no molecule/method allowlist |
| Executors | Linux x86_64 local detached workers and a dedicated Task Spooler queue |
| Reproducibility | Fixed Git commit/blob or content-addressed bundle, execution manifests, durable intent/receipts |
| Results | Immutable raw snapshots/collections, expected-record checks, signed pinned pagination |
| Integrations | Six common tools through local CLI/RPC, authenticated MCP, trusted GitHub Issue gateway |
| Model clients | OpenAI Responses, Anthropic Messages, Gemini Interactions; explicit model and API budget |
| Publication | Separate operator-authorized directory/GitHub/Artifact workflows with immutable references |
| Extension | Installed, administrator-approved engine/executor entry points; independent demo plugin |

Python 3.11–3.13. macOS supports core/client/schema work; native execution requires
Linux x86_64. Model SDKs are optional extras. Commercial QC programs are separately
licensed and installed by the site; no binaries or credentials are bundled.

## Boundaries

Native scripts and plugins are trusted code, **not a sandbox or public multi-user
execution service**. CPU affinity/thread settings are not exclusive allocation;
memory is advisory. `walltime_seconds: null` has no framework calculation timeout,
but an explicit site cap rejects incompatible requests. Chat/API time budgets do
not cancel computations.

`COMPLETED`, verified files, complete declared quantities and scientific acceptance
are separate. `data_ready` requires `COMPLETED + VERIFIED + COMPLETE`;
`scientific_acceptance` defaults to `NOT_EVALUATED`. Synthetic demos and parser
fixtures do not establish scientific validity or every QC-version compatibility.

See the evidence matrix for actual native, fixture, SDK, API and product coverage.
No paid model calls, real external publication or production migration were used
to prepare this local candidate.

## License and contributions

New project code is Apache-2.0; see [LICENSE](LICENSE),
[source inventory](docs/source-inventory.md), [CONTRIBUTING](CONTRIBUTING.md) and
[SECURITY](SECURITY.md). External programs and dependencies retain their own terms.
