# v0.1 implementation progress

The approved Native implementation is active. This is not a release acceptance report.

| Stage | State | Current evidence |
|---|---|---|
| A1–A5 core | Complete | macOS Python 3.13: 86 passed, 3 Linux-only skips; isolated Linux x86_64 Python 3.13: 113 passed after worker hardening |
| B compute/plugins/results | In progress | B1/B2 complete: isolated plugins and real detached local worker; B3 Task Spooler in progress |
| C integrations | Pending | No real provider or production credentials used |
| D release | Pending | No release/publication claim |

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
