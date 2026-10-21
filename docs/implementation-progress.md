# v0.1 implementation progress

The approved Native implementation is active. This is not a release acceptance report.

| Stage | State | Current evidence |
|---|---|---|
| A1–A5 core | Complete | Frozen identity, authentication, durable intent and six shared tools |
| B1–B5 compute/plugins/results | Complete | Isolated plugins, real Linux local/Task Spooler workers, synthetic QC profiles, immutable collections |
| C1–C5 integrations | Complete at offline/SDK level | GitHub/MCP/three clients/publication; no real external API operations |
| D1–D2 compatibility/docs | Complete | Read-only legacy identity and clean wheel/demo installation |
| D3 release | In final verification | Python matrix, package rebuild, independent review and local candidate artifacts |

Existing compute deployments remain untouched. Linux checks use a new local VM with no host-directory mounts. All source implementation so far is newly written from the approved contracts; no private source/history/results copied.

Implementation rulings: preserve A1–D3 task IDs despite numeric-only skill helpers; source freeze optionally accepts the full execution manifest; avoid site-specific path blacklists in reusable code and require explicit private roots instead. Further decisions and exact commands are recorded in the execution ledger and will be consolidated in release acceptance documentation.

## B3 — isolated Task Spooler

Implemented a dedicated explicit socket, server boot/PID/start/socket/binary identity, full queued-command hashes and immutable scheduler receipts. Read operations cannot start a replacement server. Queued-response loss is reconciled without a new enqueue. Reused numeric IDs do not override historical terminal evidence. Memory remains advisory.

Evidence: macOS full suite **107 passed, 15 Linux-only skipped**; new isolated Linux x86_64 full suite **122 passed** (237.54 s), including five real Task Spooler scenarios. No legacy queue or n008 connection.

## B4 — native QC profiles

Original PySCF, ORCA and Molpro adapters are registered through installed entry points. Native molecule/method content is unrestricted; parser support is separately declared. Synthetic fixtures cover script evidence, ordered ORCA gradients, explicit Molpro TABLE metadata and a conservative XML subset. Missing XML convergence or ambiguous gradient ownership stays unverified. No private legacy code/results or licensed binaries were copied.

Evidence: macOS full suite **129 passed, 15 Linux-only skipped**; isolated Linux full suite **144 passed** (266.03 s). ORCA/Molpro native software and numerical accuracy have not been live validated.

## B5 — immutable declared results

The broker writer reconciles independently of API reads, recovers reservations, observes native terminal receipts and copies bounded regular outputs to immutable snapshots. Collections bind parser/assessment code, declared contract and raw evidence. Cursor HMACs bind run, collection, fields and offset; newer indexes do not redirect old pages. Unsupported/missing evidence, invalid values and missing quantities remain distinct. Terminal execution is not downgraded by later collection failures.

Evidence: macOS full suite **149 passed, 17 Linux-only skipped**; isolated Linux full suite **166 passed** (312.40 s), including native collect/read and output-symlink rejection. No scientific acceptance was performed.

## C1 — authenticated GitHub gateway

Trusted Actions events are bound to a fetched Issue, fixed repository ID and allowlisted stable author/actor IDs. The gateway persists validate output and an Issue intent before submission. Edited frozen Issues conflict, retries retain one intent, and fixed Git tree/blob evidence is staged in a credential-free cache. The composite Action checks an administrator-installed pinned version; it does not install or execute task code.

Evidence: macOS complete suite **161 passed, 17 Linux-only skipped**; isolated Linux GitHub/source/Action tests **23 passed**. GitHub API traffic was simulated; no real repository, Issue, run or publication was created.

## C2 — authenticated MCP

MCP SDK 2.3.0 exposes exactly the shared six schemas. Stdio derives local OS identity; loopback HTTP uses private expiring opaque bearer digests and stateless per-request context. Remote deployment needs a configured TLS gateway. No OAuth server or universal web-product compatibility is claimed.

Evidence: actual SDK in-memory/ASGI tests **7 passed**; minimal-core macOS full suite **163 passed, 22 skipped** (17 Linux and 5 optional SDK tests, the latter executed separately). No model account, external server or paid API call.

## C3 — optional provider adapters

OpenAI Responses, Anthropic Messages and Gemini Interactions retain the same schemas and correlate results using the original provider call ID. They reject partial/invalid calls and preserve continuation metadata. SDKs are imported only on explicit connection; models are explicitly chosen.

Evidence: **24 provider protocol tests passed**; three separately installed optional environments imported/constructed SDK clients with sockets forbidden: OpenAI 3.36.0, Anthropic 1.17.0, Google GenAI 2.32.0. API calls: **0**. Minimal-core macOS full suite **187 passed, 22 explicit skips**.

## C4 — durable human intent and tool loops

Private SQLite client sessions bind an authenticated site/principal, explicit human request ID, validated task and one durable submission key. Unknown dispatches resume the saved batch; provider switches retain the same calculation intent. Explicit reruns reference an existing run. Chat budgets do not cancel computation or change its walltime.

Evidence: **34 client/cross-provider tests passed** on macOS and isolated Linux, including real broker idempotency with a test executor, parallel key reservations, lost dispatch and provider-switch retries. Minimal-core macOS full suite **197 passed, 22 explicit skips**. All provider responses were synthetic; API calls remain zero.

## C5 — immutable publication mechanisms

Operator-only publishers verify all derived/raw files, export directories, preserve unknown GitHub writes, forbid force updates and serialize first-publication reservations. Actions archives have deterministic tar hashes plus separately checked Artifact ZIP digests. API readback loss retains upload identity; expiry/renewal appends references without changing numerical collections. Six chat tools remain unchanged.

Evidence: macOS complete suite **213 passed, 23 skipped** (17 Linux + 5 MCP SDK + 1 HTTPX serializer); isolated Linux full suite **230 passed, 6 optional skips** (310.94 s). The real HTTPX serializer test passed separately in a fresh GitHub-extra environment. All GitHub/Artifact services were simulated; no remote writes/uploads occurred.

## D1 — read-only legacy compatibility and rights inventory

The offline inspector preserves original bytes, canonicalization algorithm and claimed digest. Authenticated old QC Issues return mappings/gaps only. Running legacy job numbers are never adopted. The source inventory records original implementation, synthetic fixtures, external dependencies and the unchanged read-only legacy reference; no private source/history/data was copied.

Evidence: **5 legacy tests passed**, read-only permissions plus before/after hashes; host full suite **218 passed, 23 explicit skips**; isolated Linux legacy/Issue/CLI tests **18 passed**. No real production snapshot or migration was performed.

## D2 — clean-site documentation and executable quickstart

English/Chinese quickstarts, plugin/site/results guides, compatibility matrix, native input examples and an uninstalled systemd template are present. The public `demo` CLI provisions only a new owned synthetic site and refuses foreign resume configuration. Test discovery is limited to tests; a frozen-input tripwire is not imported. Historical design-only status was reconciled with current evidence.

Evidence: docs/guard tests **4 passed**; minimal-core host full suite **222 passed, 24 skips**; Linux docs plus fresh wheel/demo installation in empty HOME **5 passed** (37.06 s). Demo resume retains run and collection IDs. The systemd template remains uninstalled/unverified; no commercial native job or paid API call was run.
