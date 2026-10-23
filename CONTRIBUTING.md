# Contributing

Use Python 3.11–3.13. Create an isolated environment, install `uv==0.11.8`, then:

```sh
uv pip install --require-hashes -r constraints/core-dev.txt
uv pip install --no-deps -e . -e examples/plugins/demo-engine
python -m pytest tests -m "not qc_live and not provider_live and not github_live" -ra
```

Native execution tests require Linux x86_64; Task Spooler tests use private sockets.
macOS is supported for core/client work. Optional SDK tests need the hashed
`constraints/tested.txt` environment. Tests discover only `tests/`, never scientific
inputs. Add a failing regression before a repair and preserve frozen identities.

Follow `docs/plugin-guide.md` for plugins and `docs/source-inventory.md` for origins.
Use synthetic fixtures with redistribution rights. Never commit credentials,
licensed programs or private research data. Do not change runtime or schema
semantics silently. Record unexecuted compatibility checks explicitly.

Contribute through [the public repository](https://github.com/binghuang2018/chat-hpc-control).
Report ordinary bugs or propose changes in [Issues](https://github.com/binghuang2018/chat-hpc-control/issues).
For sensitive reports, follow SECURITY.md and omit credentials/private research data.

Full evidence/build instructions: [validation guide](docs/validation-guide.md).
