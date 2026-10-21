# Reproducing the offline release checks

Use an isolated checkout and new runtime directories. No production node,
credentials, paid model call or commercial QC executable is needed.

## Core/platform matrix

```sh
uv venv --python 3.13 .venv
uv pip install --require-hashes -r constraints/core-dev.txt
uv pip install --no-deps -e . -e examples/plugins/demo-engine
.venv/bin/python tools/record_validation.py --name local-core --evidence private-evidence -- \
  .venv/bin/python -m pytest tests -m "not qc_live and not provider_live and not github_live" -ra
```

Repeat with Python 3.11 and 3.12 on Linux x86_64 and macOS. Linux tests build and
install fresh wheels for native/plugin and empty-HOME CLI tests. Install Task
Spooler separately on the test host, with `tsp` on PATH; every TS test uses its
own temporary socket. Tests never inspect an existing queue. Without it, record
the explicit skips rather than claiming Task Spooler compatibility.

The source tree must be unchanged during a run. Linux VM results are separate
from host results. A before-fix full suite plus a final targeted regression is
reported as those two pieces of evidence, not as one final full suite.

## SDK checks without API calls

Install `constraints/tested.txt` in another new environment, then the editable
project with `--no-deps`. Run the full non-live suite and:

```sh
python scripts/check_optional_sdk.py openai
python scripts/check_optional_sdk.py anthropic
python scripts/check_optional_sdk.py gemini
```

The import checks empty HOME/environment and forbid DNS/socket connections. The
actual Google SDK retry test injects HTTPX MockTransport, including a failed HTTP
response; it makes zero remote requests. MCP tests use actual SDK in-memory and
loopback ASGI clients. GitHub tests use simulated services, including lost replies.

## Local distribution

```sh
python -m build --no-isolation --outdir dist
python -m build --wheel --no-isolation --outdir dist examples/plugins/demo-engine
python -m twine check --strict dist/*
python tools/release_manifest.py --dist dist --evidence private-evidence --output dist/release-manifest.json
```

Run twine before adding JSON/checksum files to dist (or pass only wheel/sdist
paths). Hash the final artifacts with SHA-256. `tests/release` checks wheel privacy,
rebuilds a wheel from sdist and imports it in a fresh environment. Release evidence
requires actual command/environment/version/log/result metadata; review its semantic
summary. A successful build alone is not functional or scientific acceptance.

Each evidence name is write-once. Choose a new name for every rerun. Interrupted
or source-changing runs retain their log without a PASS record. PASS records bind
the log SHA-256 at capture, and the manifest rejects changed logs.

Captured local logs can contain temporary developer/test paths. Keep them private;
distributed wheels/sdist must not contain those logs, runtime files or credentials.
Do not commit a private evidence directory. The tracked acceptance report summarizes
actual observations without copying credentials, research inputs or site configuration.
