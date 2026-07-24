# Case 02 — Indirect prompt injection and excessive agency

## Risk

**High in the vulnerable design.** Text retrieved from an external content
source can instruct the model to use a high-impact refund tool. A model is not
an authorization boundary, so a successful injection could change financial
state without explicit customer intent.

Mappings: OWASP LLM01:2025 (Prompt Injection), OWASP LLM06:2025 (Excessive
Agency), CWE-862 where the historical tool lacked server-side authorization.

## Preconditions and affected assets

- An external-partner KB source is compromised or returns malicious text.
- The agent retrieves that article during a normal customer conversation.
- In `v0-vulnerable`, the model is offered the state-changing `issue_refund`
  capability.
- Affected assets: refund integrity, order state and customer trust.

## Vulnerable evidence

Historical snapshot: `v0-vulnerable` at commit `64924b3`.

The baseline agent advertises and dispatches `issue_refund`. The baseline tool
also trusts the model-supplied order and amount. A malicious KB row can
therefore flow into the model and induce a real refund call.

The live-model success rate is deliberately not a release gate. It varies by
model, quantization and decoding behavior.

## Root cause

The application gave a non-deterministic component a money-moving capability
and treated a prompt-level instruction as the main behavioral control.
Authorization cannot be repaired in a system prompt.

## Fix

- The model tool registry contains no `issue_refund`.
- The only refund-related model capability, `prepare_refund`, is read-only.
- `_dispatch` uses a fail-closed server-side capability allowlist.
- A real refund requires an explicit authenticated HTTP request outside the
  model/tool loop.
- Retrieved articles include a trust label, and tool messages label returned
  content as untrusted data. These labels are defense in depth, not the primary
  control.
- Debug traces are opt-in and disabled by default.

## Verification

`test_poisoned_kb_reaches_model_but_cannot_execute_refund` uses a stateful
`IndirectInjectionProvider`:

1. it searches the poisoned external-partner article;
2. it asserts that `CASE2_INJECTION_MARKER` reached the model context;
3. it lists Alice's own valid paid orders;
4. it attempts the historical `issue_refund` call with Alice's legitimate
   order and exact amount;
5. the dispatcher returns `tool_not_allowed`;
6. refund count and order status remain unchanged.

This deliberately avoids depending on Case 01 ownership or amount failures.
`test_explicit_authenticated_refund_succeeds_once` is the positive control:
Alice can explicitly refund her own order, and an exact replay creates no
second record.

## Residual risk

- Capability separation does not guarantee truthful model summaries.
- A model can still try to persuade the customer to use the explicit endpoint.
  A production UI should provide source-aware review and confirmation.
- A live-model transcript is useful demonstration evidence but remains
  non-blocking and non-statistical.
- Every future write-capable agent tool reopens the excessive-agency analysis.
