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
