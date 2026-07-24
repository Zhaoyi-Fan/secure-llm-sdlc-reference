# Case 01 — Broken object-level authorization

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

## Verification

`tests/test_case_01_object_authorization.py` proves:

- a customer can still read its own order;
- the same customer receives 404 for another customer's order;
- a cross-customer refund produces no refund row and no status change;
- negative and non-full amounts are rejected.

The positive control prevents a false pass caused by disabling order access.

## Residual risk

Integer IDs remain guessable, but guessing no longer grants access. Any future
batch, export, admin or background-job path must apply the same principal scope
or a separately reviewed privileged policy.
