# Publication and raw-result access

Publication is a separate operator/Actions operation, with `results:publish` plus
normal result-read ownership. None of the six chat tools publishes, installs,
cancels or selects a publication target. Target paths/repositories/branches and
credential environment variable names are private operator configuration.

## Local directory

```toml
[settings.publish_targets.local-export]
kind = "directory"
path = "/example/exports"
snapshot_store = "/example/private/state/snapshots"
```

```sh
chat-hpc-control --site /example/private/site.toml publication publish \
  --target local-export --collection-root /example/private/state/snapshots/collections/RUN/COLLECTION
```

The command asks the live broker to authorize the pinned collection. It verifies
every collection and raw file, rejects linked exports, and writes immutable
content. Repeating a publication does not replace files. A directory reference is
local-only; a remote chat cannot download a Mac/Linux path by itself.

## GitHub and large raw evidence

```toml
[settings.publish_targets.raw-artifacts]
kind = "artifact"
repository = "example-lab/qc-results"
stage_root = "/example/control/artifact-stage"
token_env = "CHC_PUBLICATION_TOKEN"

[settings.publish_targets.results-commit]
kind = "github"
repository = "example-lab/qc-results"
branch = "results" # create and protect this branch separately
state_root = "/example/control/publication-state"
inline_bytes = 1048576
# Large bundles use append-only verified upload receipts for this collection:
artifact_receipts_dir = "/example/control/artifact-stage/receipts"
```

`examples/github/publish-results.yml` demonstrates the two-phase workflow. Adjust
the repository, role, labels, fixed paths, protected environment and receipt
directory before enabling it. The submission workflow has read permissions;
publication runs with a separate write credential on the publication gateway.
It never downloads or executes QC input code. The official upload Action is
pinned to a verified full commit; no external workflow was run in acceptance.

1. `publication stage` builds a deterministic `.tar.gz` and records its SHA-256.
2. The official Artifact Action uploads that **fixed path** in a trusted Actions
   runtime, using a name bound to collection/run/attempt.
3. `publication record-upload` verifies the local tar digest, Actions output ID,
   ZIP digest, fixed repository/run/name and API readback/retention. Outside an
   Actions runtime it cannot attest a successful upload. The tar digest and
   Artifact ZIP digest are distinct; downloaders verify both applicable layers.
4. `publication publish` publishes small collection files at a fixed Git commit.
   Larger raw data requires a verified Artifact receipt. Git updates always use
   `force:false`. Branch conflicts or lost replies retain `PUBLISH_UNKNOWN`;
   reconciliation reads fixed content/ancestry without creating another commit.

Verified publication receipts are appended under the site's publication index.
`get_result_manifest` exposes their immutable commit/Artifact references to an
authorized remote client. Repository/Artifact access still requires appropriate
GitHub permissions. The broker only reads these local receipts and holds no
publication token.

## Expiry and renewal

Artifact expiry changes download availability, not stored numerical completeness
or scientific acceptance. Respect `expires_at` even on an older upload receipt.
`ArtifactBackend.reconcile_publish` can refresh availability; it performs no
calculation. `renew` reports `RENEWAL_REQUIRED`: run a new explicitly authorized
upload, then record it with `previous=old_receipt` (CLI `--previous-receipt`).
Renewal requires a new Artifact ID and the same archived content; it appends a
receipt, preserving old collections and Git commits. There is no automatic
Artifact upload from an ordinary machine or model call.

Evidence covers local directory exports, simulated GitHub branch conflicts/lost
responses, Artifact expiry/renewal and a real HTTPX request serializer on a mock
transport. It does not establish a live GitHub upload or publication.

References: [Artifact API](https://docs.github.com/en/rest/actions/artifacts),
[official upload action](https://github.com/actions/upload-artifact),
[Git refs API](https://docs.github.com/en/rest/git/refs).
