# Case 01 — Broken object-level authorization

**Layer:** conventional API/AppSec authorization in an LLM-enabled
application. This flaw does not require a model, but the same server-side
ownership rule must protect both HTTP routes and agent tools.

## Risk

**High.** A valid customer could read another customer's order and issue a
refund against it by changing the numeric order ID. This compromises order
confidentiality and financial-state integrity.

Mappings: CWE-639, OWASP API Security API1:2023, OWASP Top 10 A01:2025.

## Preconditions and affected assets

- The attacker has any valid customer account.
- The attacker can discover or guess another integer order ID.
- Affected assets: order item, value, status, customer note and refund state.

## Vulnerable evidence

Historical snapshot: `v0-vulnerable` at commit `64924b3`.

After seeding the local lab, Alice can request Bob's order ID and receive HTTP
200. The same principal can call the refund endpoint for Bob's order because
`current_user_id` is accepted by the function but omitted from its SQL query.

The vulnerable read and refund lookups use only the globally unique object ID:

```python
# v0-vulnerable
"FROM orders WHERE id = ?"
(order_id,)
```

The function receives `current_user_id`, but this value never participates in
the authorization decision. See the immutable V0 source for
[`get_order`](https://github.com/Zhaoyi-Fan/secure-llm-sdlc-reference/blob/64924b3c413780ddc8812797652a7dc29ba5ebcb/app/tools.py#L20-L27)
and
[`issue_refund`](https://github.com/Zhaoyi-Fan/secure-llm-sdlc-reference/blob/64924b3c413780ddc8812797652a7dc29ba5ebcb/app/tools.py#L30-L48).

## Root cause

Authorization existed at the route boundary only as “the caller is logged in.”
The data-access query selected an object by globally unique ID without scoping
that object to the authenticated principal. The refund path repeated the same
mistake.

## Fix

- `get_order` queries by both `order_id` and the server-supplied user ID.
- `issue_refund` applies the same ownership scope inside the transaction.
- Non-owned and nonexistent objects use the same 404 response.
- The API never accepts a user ID from the request body or model arguments.
- Full-refund amount, allowed state and one-refund-per-order invariants are
  enforced server-side.

The central ownership change is small but security-critical:

```python
# v1.0.0 / hardened main
"FROM orders WHERE id = ? AND user_id = ?"
(order_id, current_user_id)
```

The same ownership predicate is applied inside the refund transaction. See the
immutable V1 source for
[`get_order`](https://github.com/Zhaoyi-Fan/secure-llm-sdlc-reference/blob/v1.0.0/app/tools.py#L22-L30)
and
[`issue_refund`](https://github.com/Zhaoyi-Fan/secure-llm-sdlc-reference/blob/v1.0.0/app/tools.py#L60-L119),
or review the complete
[`v0-vulnerable...v1.0.0` comparison](https://github.com/Zhaoyi-Fan/secure-llm-sdlc-reference/compare/v0-vulnerable...v1.0.0).

## Verification

[`tests/test_case_01_object_authorization.py`](../../tests/test_case_01_object_authorization.py)
proves:

- a customer can still read and refund its own order;
- the same customer receives 404 for another customer's order;
- a cross-customer refund produces no refund row and no status change;
- negative and non-full amounts are rejected.

The positive controls prevent a false pass caused by disabling order access or
refunds. For a safe automated V0 replay and an optional loopback-only manual
comparison, follow the [Case 1 guided lab](../case-01-lab.md).

## Residual risk

Integer IDs remain guessable, but guessing no longer grants access. Any future
batch, export, admin or background-job path must apply the same principal scope
or a separately reviewed privileged policy.
