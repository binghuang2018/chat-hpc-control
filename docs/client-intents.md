# Durable client intents

Use `ClientSessionStore` on a private local filesystem. Bind it to an authenticated
site/principal, then explicitly call `begin_request(request_id, prompt)` before
`run_turn`. Reuse **the same request ID and prompt** after a timeout, restart or
provider switch. A session cannot be rebound to another identity.

A successful `validate_task` result is saved before any submit. The model must
supply its fixed task and manifest; the client replaces the model's proposed
idempotency key with its own durable key. Provider call IDs are used only to
correlate/replay call results. One human request has one calculation slot. For a
campaign, use one frozen multi-system script or explicit independent request IDs.

A new request for an already reserved manifest requires an explicit `rerun_of`
referencing the previous run. A model cannot authorize that change or select a
new slot after a timeout. Unknown submissions retain their key and pending call;
recovery retries that intent through the broker. No cancellation, hidden compute
walltime or new computation is inferred from API failure.

Client round/call/output-token budgets bound chat work only. SDK automatic retries
are disabled for the configured adapters. Provider continuation metadata and
pending complete responses are saved locally; partial/malformed responses execute
nothing. Tool outputs, including instructions embedded in native logs, remain
encoded tool data. The loop exposes no shell or administrative tool.

`examples/clients/chat.py` is an explicit control-gateway example. It requires a
provider, model, API-key environment variable name, private session path, site,
request ID and prompt. **The acceptance suite does not run paid examples.**
Supply your own authenticated dispatch callback for another transport; the
reference example uses a local Unix broker socket.

Sessions contain prompts, native-task metadata and model response state; protect
and retain them as private data. They never store the provider API key. Environment
filtering is not an OS sandbox: deploy untrusted native work behind the required
user/container/host boundary before putting real credentials on a gateway.

The returned `state` describes the **client loop**, not execution or scientific
completion. Query the run's execution state and collection summary separately.
