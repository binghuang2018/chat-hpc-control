# Tested dependency snapshots

`core-dev.txt` and `tested.txt` were resolved with uv 0.11.8 using universal
Python >=3.11 resolution and full package hashes. They pin the actual tested
SDK versions, including Google GenAI 2.32.0's explicit no-retry compatibility
handling. These are release validation snapshots, not claims that every future
version in the metadata's supported ranges has been tested.

```sh
uv pip install --require-hashes -r constraints/core-dev.txt
# Optional complete offline SDK validation environment:
uv pip install --require-hashes -r constraints/tested.txt
```

The minimal developer snapshot deliberately excludes model SDKs; optional
integrations are tested in the separate complete snapshot. Core runtime imports
remain free of those extras. Source/editable installs in CI use `--no-deps` only
after installing the complete chosen snapshot.

Re-resolve deliberately, review version changes, rerun SDK MockTransport and
platform tests, then update the acceptance evidence. Hashes prove package-byte
identity; they are not a dependency security assessment.
