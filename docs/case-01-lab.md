# Case 01 lab — broken object-level authorization

This lab shows a conventional API authorization failure inside an LLM-enabled
application. No model is required. The same object-ownership policy must protect
direct HTTP routes and any agent tool that reaches them.

## Security outcome

Alice is authenticated, but Bob owns the target order.

| Check | `v0-vulnerable` | Hardened `main` / `v1.0.0` |
|---|---:|---:|
| Alice reads her own order | `200` | `200` |
| Alice refunds her own paid order | `200` | `200` |
| Alice reads Bob's order | `200` — vulnerable | `404` — blocked |
| Alice refunds Bob's order | `200` — vulnerable | `404` — blocked |
| Bob's order after the attempt | `refunded` | `paid` |

The legitimate operations are positive controls: V1 passes because it enforces
ownership, not because order access or refunds were disabled.

> **Local-lab boundary:** use only the fictional data in this repository, bind
> Uvicorn to `127.0.0.1`, and never deploy `v0-vulnerable`. The manual checks
> intentionally change the selected disposable database. Re-seed before every
> run and follow the cleanup steps.

## Path A — safe deterministic verification

This is the recommended first path. It opens no listening port, calls no model,
exports V0 to a temporary directory and deletes the temporary database on exit.
Run it from a complete clone of hardened `main` that contains the
`v0-vulnerable` tag.

Windows PowerShell, without relying on script activation:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m scripts.reproduce_v0
.\.venv\Scripts\python.exe -m pytest -q tests/test_case_01_object_authorization.py
```

The V0 replay should include:

```json
{
  "case_1": {
    "cross_customer_read_http_status": 200,
    "cross_customer_read_reproduced": true,
    "cross_customer_refund_http_status": 200,
    "cross_customer_refund_reproduced": true
  }
}
```

The focused V1 regression should pass all Case 1 tests. See the complete
[V0 reproduction report](v0-reproduction-report.md) for the replay's safety and
cleanup properties.

## Code comparison

V0 accepts `current_user_id` but does not use it in either object lookup. Knowing
or guessing an order ID is therefore enough to cross the ownership boundary.

```python
# v0-vulnerable: app/tools.py
def get_order(order_id: int, current_user_id: int) -> dict | None:
    row = conn.execute(
        "SELECT ... FROM orders WHERE id = ?",
        (order_id,),
    ).fetchone()

def issue_refund(order_id: int, amount_cents: int, current_user_id: int) -> dict:
    order = conn.execute(
        "SELECT ... FROM orders WHERE id = ?",
        (order_id,),
    ).fetchone()
```

V1 binds the trusted server-supplied principal into the read and mutation
transaction:

```python
# v1.0.0 / hardened main: app/tools.py
row = conn.execute(
    "SELECT ... FROM orders WHERE id = ? AND user_id = ?",
    (order_id, current_user_id),
).fetchone()

order = conn.execute(
    "SELECT ... FROM orders WHERE id = ? AND user_id = ?",
    (order_id, current_user_id),
).fetchone()
```

Review the pinned
[V0 source](https://github.com/Zhaoyi-Fan/secure-llm-sdlc-reference/blob/64924b3c413780ddc8812797652a7dc29ba5ebcb/app/tools.py#L20-L48),
[V1 source](https://github.com/Zhaoyi-Fan/secure-llm-sdlc-reference/blob/v1.0.0/app/tools.py#L22-L119),
or the immutable
[`v0-vulnerable...v1.0.0` comparison](https://github.com/Zhaoyi-Fan/secure-llm-sdlc-reference/compare/v0-vulnerable...v1.0.0).

## Path B — manual V0/V1 HTTP comparison on Windows

This path starts each snapshot locally and uses the same HTTP driver against
both. The driver logs in as Alice and Bob, discovers paid orders dynamically,
runs legitimate positive controls, attempts the two cross-customer operations,
and prints a token-free JSON summary.

### 1. Prepare a full clone and Python environment

```powershell
git clone https://github.com/Zhaoyi-Fan/secure-llm-sdlc-reference.git supportassist-case1
Set-Location .\supportassist-case1
git rev-parse "v0-vulnerable^{commit}"
git rev-parse "v1.0.0^{commit}"

py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

$main = (Get-Location).Path
$python = Join-Path $main ".venv\Scripts\python.exe"
$v0Lab = Join-Path (Split-Path $main -Parent) "supportassist-v0-lab"
$v1Lab = Join-Path (Split-Path $main -Parent) "supportassist-v1-lab"
git worktree add --detach $v0Lab v0-vulnerable
git worktree add --detach $v1Lab v1.0.0
```

The two commit checks must resolve to:

```text
64924b3c413780ddc8812797652a7dc29ba5ebcb
a03d6d6c9b10b01531f7b6b607bd04b98f945f9e
```

### 2. Start the isolated V0 API

In terminal 1:

```powershell
Set-Location $v0Lab
$env:DB_PATH = Join-Path $v0Lab "case1-v0.db"
$env:JWT_SECRET = (& $python -c "import secrets; print(secrets.token_urlsafe(48))")
& $python -m app.seed
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

No Ollama or LM Studio process is needed for Case 1.

### 3. Reproduce V0

In terminal 2, opened in the `supportassist-case1` main clone:

```powershell
.\scripts\run_case_01_manual.ps1 -BaseUrl "http://127.0.0.1:8000" -Expected v0
```

Expected evidence:

```json
{
  "positive_control": {
    "read_http_status": 200,
    "refund_http_status": 200
  },
  "cross_customer_attempt": {
    "principal": "alice",
    "target_owner": "bob",
    "before_status": "paid",
    "read_http_status": 200,
    "refund_http_status": 200,
    "after_status": "refunded"
  },
  "expectation_met": true
}
```

This demonstrates both BOLA impacts: unauthorized disclosure and unauthorized
financial-state mutation.

### 4. Start a fresh V1 API

Stop V0 with `Ctrl+C` in terminal 1. Then, still in terminal 1:

```powershell
Set-Location $v1Lab
$env:DB_PATH = Join-Path $v1Lab "case1-v1.db"
$env:JWT_SECRET = (& $python -c "import secrets; print(secrets.token_urlsafe(48))")
& $python -m app.seed
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 5. Verify V1 with the same checks

In terminal 2:

```powershell
.\scripts\run_case_01_manual.ps1 -BaseUrl "http://127.0.0.1:8000" -Expected v1
```

Expected evidence:

```json
{
  "positive_control": {
    "read_http_status": 200,
    "refund_http_status": 200
  },
  "cross_customer_attempt": {
    "principal": "alice",
    "target_owner": "bob",
    "before_status": "paid",
    "read_http_status": 404,
    "refund_http_status": 404,
    "after_status": "paid"
  },
  "expectation_met": true
}
```

The uniform `404` does not reveal whether the object exists for another user.
Bob's unchanged `paid` state proves the failed request did not mutate data.

### 6. Cleanup

Stop V1 with `Ctrl+C`. In terminal 1, keep the resolved `$main`, `$v0Lab` and
`$v1Lab` values from the setup steps and remove only the two named lab databases
and the two dedicated worktrees:

```powershell
Set-Location $main
Remove-Item -LiteralPath (Join-Path $v1Lab "case1-v1.db") -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $v0Lab "case1-v0.db") -ErrorAction SilentlyContinue
git worktree remove $v0Lab
git worktree remove $v1Lab
Remove-Item Env:DB_PATH -ErrorAction SilentlyContinue
Remove-Item Env:JWT_SECRET -ErrorAction SilentlyContinue
```

## Interpretation

Case 1 is not an LLM-specific vulnerability. It demonstrates that ordinary
authorization controls remain mandatory around an agent application: every
route and tool must bind the requested object to the authenticated principal.
The model must never be trusted to supply or enforce identity.

Continue with the detailed
[finding-to-fix record](findings/case-01-object-level-authorization.md).
