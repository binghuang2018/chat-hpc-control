# Provider compatibility

Adapters share all six tool schemas and preserve required/nullable fields. They
perform complete-message and argument validation before dispatch. The broker
remains authoritative for identity, scope and execution policy. SDKs are lazy
optional dependencies; provider credentials belong to the control client, never
the native worker environment.

| Adapter | API family | Tested SDK | Evidence | Real API / web product |
| --- | --- | --- | --- | --- |
| OpenAI | Responses function calling | `openai 3.36.0` | synthetic protocol, offline SDK import | not exercised |
| Anthropic | Messages client tools | `anthropic 1.17.0` | synthetic protocol, offline SDK import | not exercised |
| Gemini | GenAI Interactions function calling | `google-genai 2.32.0` | synthetic protocol, offline SDK import | not exercised |
| MCP | SDK 2.x stdio / Streamable HTTP | `mcp 2.3.0` | real SDK in-memory and local ASGI HTTP | remote chat product not exercised |
| GitHub | REST tree/blob/Issue and trusted Actions event | HTTPX optional | fixed mocked API responses | no live repository run |

No default model IDs are embedded. Users choose a model, credentials and API
budget explicitly when connecting a client. Library construction and import do
not make a model request. Tests create clients with unmistakably synthetic keys, an empty HOME,
and forbid DNS/socket connections. A real Google SDK HTTPX mock test also verifies
that one failed request produces no hidden retry; no remote request is made.

OpenAI tools explicitly use `strict: false`: the full TaskSpec includes extensible
plugin options and does not satisfy the closed-object strict-mode restrictions.
The complete original schema is retained, including nullable fields. This is not
a relaxation of server validation. Provider schema acceptance can vary by model;
these tests do not establish remote API acceptance of every nested schema.

Continuation retains OpenAI output items (including reasoning metadata),
Anthropic assistant content (including signed thinking blocks), and Gemini's
`previous_interaction_id`. Results are encoded as tool data with original call
IDs, never interpreted as new control instructions. Call IDs are correlation
metadata, not calculation idempotency keys.

Official references checked 2026-10-22:

- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [Anthropic tool definitions](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools)
- [Anthropic tool results](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls)
- [Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling)
- [MCP tools](https://py.sdk.modelcontextprotocol.io/servers/tools/)

The compatibility claim has four distinct levels: implemented contract, offline
simulation/SDK verification, real API verification, and real product verification.
Only the first two are established for the model adapters in this release.
