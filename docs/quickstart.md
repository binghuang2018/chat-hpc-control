# Clean Linux quickstart

Requirements: **Linux x86_64, Python 3.11–3.13**. No QC program, account, API key,
root access, existing runner or Task Spooler is needed. Use a short new private
path; the demo refuses a nonempty foreign directory.

From the local release folder, install the two wheels in a fresh environment:

```sh
python3 -m venv /tmp/chc-venv
/tmp/chc-venv/bin/python -m pip install ./dist/chat_hpc_control-0.1.0-py3-none-any.whl ./dist/chat_hpc_demo_engine-0.1.0-py3-none-any.whl
/tmp/chc-venv/bin/chat-hpc-control demo --root /tmp/chc-demo
```

For a source checkout, build the wheels first (builds are local):

```sh
python3 -m pip install build
python3 -m build --outdir dist
python3 -m build --wheel --outdir dist examples/plugins/demo-engine
```

The demo creates an isolated `example-demo` site, starts its own broker, imports a
synthetic bundle and uses public CLI commands to **validate → submit → status →
results**. It saves `site.toml`, `validated-task.json`, `submission.json`, private
logs and `quickstart-evidence.json` under the selected root. The output must show
`execution_state: COMPLETED`, a `collection_id`, `synthetic: true`, and
`data_ready: false`. No scientific contract was declared; that false value is
intentional. The synthetic energy is not a physical result.

Repeat safely with the same site and saved intent:

```sh
/tmp/chc-venv/bin/chat-hpc-control demo --root /tmp/chc-demo --resume
```

The run ID remains unchanged. A client wait ending is not a new computation.
`--wait-seconds` bounds the demonstration's control wait, not calculation walltime.
The demo stops only the broker process it created; native workers have independent
lifetimes. External cgroup/service behavior still needs site deployment validation.

## Inspect the public commands

While an independently started broker is running:

```sh
chat-hpc-control --site /example/private/site.toml capabilities
chat-hpc-control --site /example/private/site.toml validate --task /example/task.json
chat-hpc-control --site /example/private/site.toml submit --task /example/validated-task.json --expected-manifest FULL_SHA256 --idempotency-key HUMAN_INTENT
chat-hpc-control --site /example/private/site.toml status RUN_ID
chat-hpc-control --site /example/private/site.toml results RUN_ID --fields record_id energy gradient
chat-hpc-control --site /example/private/site.toml manifest RUN_ID
```

Save validation's returned fixed task and manifest before submit. Reuse the same
intent key after uncertain responses. Explicit reruns use a new human intent and
`--rerun-of RUN_ID`. Do not substitute a moving Git branch at submit time.

`examples/tasks/*/task.json` use an all-zero **placeholder bundle ID**. Import the
listed regular input files with `bundle import`, then put its real digest in the
task. They are schema examples, not pre-registered inputs. Start with `demo`;
PySCF/ORCA/Molpro examples require separately installed software and configuration.

The acceptance test installs freshly built wheels in an empty HOME, outside the
source checkout, and repeats this exact demo command. It does not import test
helpers, existing scientific environments or production settings.
