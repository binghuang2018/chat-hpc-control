# Results: execution, integrity, quantities and science

| Dimension | Meaning |
| --- | --- |
| `execution_state` | Observed native reservation/queue/run/terminal state |
| `integrity` | Input, run identity, terminal and raw snapshot evidence closure |
| `completeness` | Expected records and requested physical quantities |
| `scientific_acceptance` | Independent scientific validation; default `NOT_EVALUATED` |
| `data_ready` | Exactly `COMPLETED + VERIFIED + COMPLETE` |

An exit code, an existing output, a finished script or a queue state is not
scientific acceptance. Synthetic fixtures are not computed energies. A complete
failed job still has `data_ready=false`.

## Declare requirements before calculation

`expected_results: null` permits raw output and execution, with numerical
completeness `UNVERIFIED`. Otherwise use `energy-gradient/v1`, declaring every
record ID, required quantities, ordered atoms, frozen XYZ geometry file/unit,
charge, multiplicity, method, basis and state. Units are `hartree` and
`hartree/bohr`; geometry comparison converts angstrom with
`0.529177210903 angstrom/bohr` and a `1e-5 bohr` component tolerance, versioned in
parser identity. This deterministic matching tolerance is not a scientific
accuracy criterion.

Record IDs must match one-to-one. No deduplication, output-count inference or atom
reordering fills gaps. Missing quantities/records are `INCOMPLETE`; definite
contradictions, malformed dimensions, duplicates or nonfinite values are `INVALID`;
unsupported profiles or absent provenance are `UNVERIFIED`. Precedence is INVALID,
UNVERIFIED, INCOMPLETE, COMPLETE. All issues are retained.

## Initial profiles

- `pyscf-json-v1`: `records.json` with schema
  `chat-hpc-control/pyscf-records/v1`; script-reported finite numerical records.
  See `examples/tasks/pyscf-h2/job.py` for the explicit format and metadata.
- `orca-single-v1` / `orca-engrad-v1`: one RHF singlet point with unique native
  method/basis/charge/geometry/version evidence; `.engrad` must agree with the
  ordered geometry and energy. Other native methods can execute with raw output,
  but are not numerically verified by these profiles.
- `molpro-table-v1`: named CSV rows, one ordered row per atom, requiring explicit
  consistent record/method/basis/state/electronic/unit metadata. Columns are
  demonstrated in the synthetic parser fixture. Evidence is table-reported.
- `molpro-xml-single-v1`: conservative explicit single-step XML binding. Missing
  convergence/method/state/geometry evidence or ambiguous gradient ownership stays
  UNVERIFIED/INVALID. Real native Molpro XML versions have not been exercised.
- `raw-only`: any enabled native input; no numerical completeness certification.

ORCA/Molpro fixtures establish parser rules only. Do not infer real software/version
or MPI compatibility from their existence. Native examples requiring licensed
software were not executed as part of the default suite.

## Immutable collection reads

The broker writer observes and collects independently of client connections.
Outputs are copied only after verified terminal evidence, with bounded regular
files, stable hashes and no symlink/special-file escape. A collection binds raw
inventory, frozen task, terminal, parser/assessment identities and declared
contract. Reprocessing creates a new collection ID; old bytes are retained.

`summary.json`, `completeness.json`, `records.json`, `provenance.json`,
`raw-manifest.json` and `collection.json` are content-addressed derived files.
Result identities use deterministic finite-number `result-json-v1`; task manifests
retain the separate float-free canonical-json-v1 rule. Invalid nonfinite records
are retained as raw evidence/issues, not rewritten into a valid number.

Use `get_task_results` with a pinned collection, selected fields and returned cursor.
Cursors bind run/collection/fields/offset using a private HMAC key. Index updates
cannot redirect an old cursor. Reads do not submit, collect, publish or cancel.
A terminal run may still have `collection_state: PENDING` or `UNVERIFIED`.

`get_result_manifest` provides raw identities and appended publication receipts.
A local path is not a remote download URL. Use fixed Git commits or authorized
Artifact references; check access permissions and expiry. Renewal changes
availability receipts, not numerical completeness or scientific acceptance.
