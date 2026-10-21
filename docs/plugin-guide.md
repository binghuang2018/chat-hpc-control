# Plugin developer guide — API 1.0

An engine is an independently installed Python distribution. The core never
installs a package named by an Issue/model. Register an entry point:

```toml
[project.entry-points."chat_hpc_control.engines"]
example-qc = "example_qc.plugin:create_plugin"
```

Use the importable types in `chat_hpc_control.contracts.plugins`, `.task`,
`.execution` and `.results`. Implement:

```python
class Engine:
    def info(self): ...       # PluginInfo, API "1.0", profiles, closed options schema
    def probe(self, runtime): ...  # ProbeReport: actual program version/identity
    def validate(self, task, context): ...  # ResolvedTask -> ValidationReport
    def prepare(self, task, context): ...  # FrozenTask -> fixed ExecutionPlan
    def parse(self, snapshot, contract): ...  # OutputSnapshot -> ParseReport

def create_plugin():
    return Engine()
```

The complete independent example is `examples/plugins/demo-engine`. Build/install
its wheel without modifying core files, add the engine runtime to the site, then
approve its **distribution name** in `[settings.plugin_allowlist]`. Metadata-only
discovery returns a `PluginDescriptor`; runtime `EngineProxy.info()` returns
`PluginInfo`. Duplicate IDs, unapproved distributions and API-major mismatches fail
before native execution.

The plugin implementation loads only in a clean installed worker, not while
listing metadata. The host substitutes actual distribution/version/code identity.
Typed RPC carries only the selected engine and minimal site context, with explicit
byte/control-time limits and no control credentials. This is an environment/API
boundary, not an OS sandbox against administrator-installed code.

## Native plans

- Use the administrator's absolute runtime executable or configured MPI launcher.
- Return argv, never a shell string or `shell=True`. Do not accept commands, cwd,
  credentials or publication destinations in `engine_options`.
- Work under `context.run_root / "work"`; frozen inputs are copied there by the
  installed native worker. Do not mutate the immutable input snapshot.
- Preserve the exact `task.resources`. Report resource capability honestly.
- Declare normal-termination evidence when the program requires more than exit 0.
- Start with `raw-only` if numerical ownership/units/method/state cannot be proved.

Input molecule/method content is not a core whitelist. Program validity is checked
by the native program; a failed native job stays failed even if useful files exist.

## Numerical profiles

A `ParseReport` must name a versioned parser identity, records and every issue.
Read only verified snapshot files, with relative paths and source locators. Bind
ordered atoms, geometry/units, charge/multiplicity, method/basis/state, actual
version and convergence evidence. Never copy expected metadata from the contract
as if it were observed; the single-record adapters use the contract's record ID
only to label one unambiguous native point.

Missing quantities are `incomplete`; definite contradictions are `invalid`;
unsupported/unreadable evidence is `unverified`. PySCF's JSON is explicitly
`script-reported`; named Molpro TABLE values are `table-reported`. Neither is an
independent scientific review. Include synthetic or redistributable failure cases,
truncation, wrong units/order, ambiguity and nonfinite-value tests.

## Executor extensions

Register `chat_hpc_control.executors` with a constructor accepting `SiteConfig`.
Implement `ExecutorPlugin` from `.contracts.plugins`: info/probe/submit/query/
reconcile. Approve a non-core distribution under `[settings.executor_allowlist]`.
The installed executor is trusted control code; it cannot be selected by import
path in a task. Preserve reservation-before-submit, uncertain outcomes, detached
lifetime and strong job identity. A scheduler number is insufficient.

No Slurm backend ships in v0.1. Do not claim compatibility until real isolated
submission/restart/reuse tests and accurate resource-enforcement evidence exist.
