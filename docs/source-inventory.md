# Source and rights inventory

Status: original implementation for the standalone v0.1 project. The owner
selected **Apache-2.0** for newly authored project code in the approved execution
instructions. External QC software, schedulers and optional SDKs are separately
installed dependencies, not redistributed inside the package.

| Material | Origin / identity | Treatment |
| --- | --- | --- |
| Core, schemas, native worker, plugins, executors, results | Newly authored in this standalone project | Apache-2.0; no private legacy source copied |
| Transport, provider clients, publishers, compatibility adapters | Newly authored from approved interfaces and published protocol rules | Apache-2.0; mock/synthetic tests |
| Independent demo plugin | Newly authored example distribution | Apache-2.0; synthetic values, not science |
| QC/parser and legacy fixtures | Newly authored minimal synthetic fixtures | No private research results or licensed output copied |
| Architecture/plans | User-approved standalone project documents | Retained with implementation/evidence status updates |
| Legacy local reference | Read-only baseline commit `e91438d870d2be4a2cd7edbee742584afaffb2cf` | Behavioral/format reference only; zero source files/history copied |
| Python dependencies / model SDKs | PyPI distributions with declared version ranges | External dependencies; resolved versions recorded in evidence |
| ORCA / Molpro / Task Spooler | External administrator-installed programs | No executables, licenses, account files or private configuration bundled |
| GitHub Actions | Official `actions/*` repositories | Referenced at independently fetched full commit SHAs; no action code vendored |

## Legacy format reference

Read-only inspection of `broker/qc_registry.py` at the reference commit established
one legacy identity rule: ASCII-escaped sorted compact JSON plus a trailing
newline, then SHA-256. The new inspector names that rule
`hpc-control-qc-json-v1`; it preserves the original bytes and claimed digest.
It never substitutes the new task canonicalization algorithm. This primitive
serialization rule was implemented anew; the reference module was not imported
or copied, and its site-specific constants were not migrated.

The old QC Issue marker and `{version,kind,task_id}` envelope are recognized only
for authenticated read-only mapping. Numeric legacy job IDs remain unadoptable.
There is no automatic home-directory scan, remote connection, live SQLite import,
runner update or production migration.

## Offline export contract

Provide an explicit snapshot root containing `legacy-index.json`:

```json
{
  "schema": "hpc-control/offline-export/v1",
  "offline": true,
  "records": [
    {
      "task_id": "synthetic-old-h2",
      "kind": "molpro",
      "manifest_file": "manifest.json",
      "digest_algorithm": "hpc-control-qc-json-v1",
      "claimed_digest": "REPLACE_WITH_ORIGINAL_DIGEST",
      "legacy_state": "RUNNING",
      "legacy_job_id": "0"
    }
  ]
}
```

```sh
chat-hpc-control legacy --snapshot /example/offline-export
```

The inspector reads bounded regular manifest/index files only, rejects links and
checks that observed bytes remain stable. It writes nothing. A verified old
manifest digest does not establish current native process identity, numerical
completeness or scientific acceptance. Unsupported algorithms, corruption and
ambiguous mappings remain explicit gaps.

Acceptance used synthetic offline copies with read-only permissions and
before/after hashes. No authorized real production snapshot was supplied or
migrated. The legacy local reference remained clean at its original commit.
