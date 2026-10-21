# v0.1 compatibility and limitations

| Area | Evidence established | Limit |
| --- | --- | --- |
| Python | 3.11–3.13 target range; actual matrix in release acceptance | 3.14+ not supported |
| Linux x86_64 | Detached local workers, independent broker, real dedicated Task Spooler, collection | No production-node/service migration |
| macOS | Core/contracts/schemas/client protocols, optional SDKs, builds | Native executor unsupported |
| PySCF | Native Python launch plan, script JSON rules; optional tiny smoke separately recorded | Script-reported evidence; arbitrary science not certified |
| ORCA | Launch plan and synthetic RHF singlet energy/gradient profiles | Native licensed installation not exercised; other methods raw-only/unverified |
| Molpro | Launch/MPI plan, synthetic named TABLE and strict XML rules | Native licensed/MPI installation not exercised; unbound evidence stays unverified |
| Resources | Initial affinity/thread environment, explicit caps/queue slots | Memory advisory; no exclusive CPU/cgroup allocation |
| Long tasks | Null walltime has no framework deadline; worker survives client/broker | External supervisors, disk quotas and machine loss remain site concerns |
| GitHub | Mocked authenticated Issue/source/publication/Artifact lifecycle, real offline HTTPX serializer | Real API/run/publication not exercised |
| MCP | Actual SDK 2.3.0 memory and local HTTP authentication tests | Remote TLS/OAuth/chat products not exercised |
| Models | Shared schema/correlation/intent tests and independent optional SDK imports | Paid APIs and web products not exercised |
| Legacy | Synthetic read-only bytes/digest/Issue mapping | No live job adoption or production data migration |
| Science | Structural/units/provenance/completeness checks | Scientific acceptance defaults to NOT_EVALUATED |

See [provider details](provider-compatibility.md), [implementation evidence](implementation-progress.md)
and [release acceptance](v0.1-acceptance.md). A skipped optional/platform test is not
a pass for that environment. Current external version availability and product
connection support require their own verification; this release does not claim
universal compatibility with every ChatGPT/Claude/Gemini website or QC version.

The contract/plugin API major version is 1; distribution version is 0.1.0. A new
QC parser identity can produce a new collection without recalculating. Input/runtime
changes require a newly validated execution identity and an explicit human intent.
No Slurm implementation, public multi-tenant sandbox, automatic commercial-software
installation or production credential provisioning ships in v0.1.
