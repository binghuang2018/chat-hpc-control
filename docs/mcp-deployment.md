# MCP gateway deployment

v0.1 implements the six common tools with **MCP Python SDK 2.3.x**. Install the
`mcp` extra in the control gateway, separate from native compute environments.
The SDK is optional for the core broker and native workers.

## Local stdio

```sh
chat-hpc-control --site /example/private/site.toml mcp --transport stdio
```

The launching OS UID must map to a configured `local_principals` entry. The
adapter forwards calls to the existing Unix broker socket; it does not start a
second broker or calculate inside the MCP process. No identity parameters are
exposed to the model.

## Authenticated Streamable HTTP

Create a private JSON file (`0600`) with `{"tokens": [...]}`. Each entry contains
`sha256` (64 lowercase hex characters of a high-entropy bearer token), `principal`,
`site_id`, `scopes` and integer Unix `expires_at`. Store the actual token only on
the client. Generate at least 32 random bytes; do not copy test tokens.

Operator-only site settings:

```toml
[settings]
mcp_tokens_file = "/example/private/mcp-token-digests.json"
mcp_host = "127.0.0.1"
mcp_port = 8000
# Required only when exposing loopback through an external TLS gateway:
mcp_external_url = "https://qc-gateway.example.org/mcp"
mcp_tls_gateway = true
```

```sh
chat-hpc-control --site /example/private/site.toml mcp --transport streamable-http
```

HTTP always binds loopback and requires authentication before request parsing.
Use an explicitly configured HTTPS reverse proxy for remote access; preserve the
Authorization header and proxy to the loopback Host. Keep the broker's trusted
`gateway_uids` narrowly configured. Token scopes are intersected with the site's
principal policy; the broker applies scopes, engine/repository allowlists and
result ownership again. Unknown/expired tokens fail closed. The server uses
stateless HTTP so authentication is established for each request, with no
cross-principal session reuse.

This is a private opaque-bearer gateway, **not an OAuth authorization server**.
It does not implement login, consent, OAuth discovery or token issuance. Chat
products requiring those flows need a separate supported identity integration;
v0.1 does not claim that every web chat can connect directly.

Tool annotations are hints, not authorization. Responses, including native logs,
are untrusted data. Disconnecting a client leaves existing native computations
running; public tools do not offer shell, cancellation, installation or admin
operations. Reads do not trigger collection or publication.

## Evidence

Tests use actual MCP SDK 2.3.0 in-memory clients and a local ASGI HTTP client:
exact schemas/annotations, identity injection rejection, expired tokens,
unauthenticated HTTP, duplicate JSON keys, and per-request principal separation.
No real chat account or remote TLS/OAuth deployment was exercised.

References: [SDK tools](https://py.sdk.modelcontextprotocol.io/servers/tools/),
[SDK authorization](https://py.sdk.modelcontextprotocol.io/run/authorization/).
