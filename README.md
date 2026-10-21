# chat-hpc-control

**Provider-neutral chat tools for reproducible HPC calculations.**

[中文说明](README.zh-CN.md) · [Architecture](docs/superpowers/specs/2026-10-21-chat-hpc-control-v0.1-design.md) · [Plugin protocol](docs/plugin-protocol-v1.md) · [Migration](docs/migration-checklist.md)

## Status

This independent project contains the **v0.1 design proposal**, dated 2026-10-21. It does not yet contain an installable Python package, a working GitHub Action, an MCP server, or provider SDK adapters. The repository and Python distribution name are `chat-hpc-control`; the proposed Python namespace is `chat_hpc_control`. Package and repository name availability has not been reserved.

The design draws on an existing private deployment. That deployment remains separately operated; its operational history is not evidence that this new project has passed integration tests. No existing server has been migrated by preparing these documents.

## Intended workflow

1. An authorized user supplies native QC inputs, including arbitrary-molecule PySCF Python scripts, ORCA inputs, or Molpro inputs.
2. The broker resolves and freezes the input bundle, validates site policy and resource declarations, then submits exactly one execution for an idempotent request.
3. A scheduler runs the calculation independently of the chat session or GitHub workflow lifetime.
4. Collection preserves raw outputs and checks declared result quantities, units, shapes, and provenance.
5. Chat clients retrieve status and immutable result references. Numerical completeness and scientific acceptance remain separate.

## Extension points

| Layer | v0.1 design target | Extension boundary |
|---|---|---|
| Chat clients | ChatGPT/OpenAI, Claude/Anthropic, Gemini | Common tool schema; provider-specific client adapters |
| Transports | CLI, GitHub Issues/Actions, MCP | Authentication and conversion to the broker contract |
| Engines | PySCF, ORCA, Molpro | Operator-installed Python entry-point plugins |
| Execution | Local process, Task Spooler | Durable submission/query interface; Slurm deferred |
| Results | Raw bundles, declared energy/gradient records | Versioned parser profiles and publishers |

These are **planned interfaces**, not a list of implemented integrations. API and web-app availability are tracked separately in the [chat integration design](docs/chat-integrations.md). Detailed specifications are currently written in Chinese; this README is the English entry point.

## Read the proposal

- [Architecture and scope](docs/superpowers/specs/2026-10-21-chat-hpc-control-v0.1-design.md)
- [Plugin protocol, task contract, and result semantics](docs/plugin-protocol-v1.md)
- [Chat tools and provider compatibility matrix](docs/chat-integrations.md)
- [Migration checklist preserving the existing deployment](docs/migration-checklist.md)
- [Community release readiness and licensing decisions](docs/release-readiness.md)

The current review milestone is the written specification. Implementation planning, package publication, and live deployment are subsequent steps.

## Contributing and licensing

Design feedback should identify the affected contract, a concrete use case, and the proposed compatibility behavior. New engine proposals should state launch requirements, licensing constraints, supported parser profiles, and unsupported result cases.

No software license has been granted in this snapshot. Apache-2.0 is proposed for project-owned code and documentation, subject to an explicit owner decision and a source-rights audit. Vendor software, licenses, binaries, private data, and credentials are excluded from the proposed community distribution. See [release readiness](docs/release-readiness.md).
