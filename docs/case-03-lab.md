# Case 03 lab — SQL injection in knowledge-base search

This lab shows a conventional SQL-injection failure inside an LLM-enabled
application. No model is required. The authenticated `/kb` route and the agent's
KB tool reach the same data-access function, so both depend on the same query
safety boundary.

## Security outcome

Alice controls the `q` parameter of `GET /kb`.

| Check | `v0-vulnerable` | `v1.0.0` |
|---|---:|---:|
| Normal `Refund policy` search | intended article | intended article |
| Sanitized `UNION SELECT` probe | three fictional user rows — vulnerable | no injected rows |
| Literal `%` search | matches KB rows as a wildcard | no results |

The normal search is a positive control: V1 passes because it binds attacker
input as a value, not because search was disabled. The `%` check separately
proves that SQL wildcard characters are treated as literal search text.

> **Local-lab boundary:** use only the fictional data in this repository, bind
> Uvicorn to `127.0.0.1`, and never deploy `v0-vulnerable`. The public payload
> retrieves only fictional usernames and the fixed marker
> `CASE3_INJECTED_ROW`; it never requests password hashes.

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
.\.venv\Scripts\python.exe -m pytest -q tests/test_case_03_sql_injection.py
```

The V0 replay should include:

```json
{
  "case_3": {
    "http_status": 200,
    "fictional_user_rows_exposed": [
      "alice",
      "bob",
      "mallory"
    ],
    "vulnerability_reproduced": true
  }
}
```

The focused V1 regression should pass all Case 3 tests. See the complete
[V0 reproduction report](v0-reproduction-report.md) for the replay's safety and
cleanup properties.

## Code comparison

V0 inserts the caller-controlled `query` directly into SQL source text:

```python
# v0-vulnerable: app/tools.py
sql = (
    "SELECT id, title, body FROM kb_articles "
    f"WHERE body LIKE '%{query}%' OR title LIKE '%{query}%'"
)
rows = conn.execute(sql).fetchall()
```

The database therefore parses injected quotes, operators and `UNION SELECT` as
SQL grammar.

V1 constructs a literal-search pattern in application memory, then passes it as
two bound values:

```python
# v1.0.0: app/tools.py
pattern = f"%{_escape_like(query)}%"
rows = conn.execute(
    "... WHERE body LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\' ...",
    (pattern, pattern),
).fetchall()
```

These are two related but distinct controls:

- parameter binding stops input from changing the SQL grammar;
- `_escape_like` makes `%`, `_` and the escape character literal, preserving
  the intended substring-search semantics.

This implementation uses a parameterized query with bound values. It does not
depend on describing SQLite's driver behavior as a separately managed
server-side prepared statement.

Review the pinned
[V0 source](https://github.com/Zhaoyi-Fan/secure-llm-sdlc-reference/blob/64924b3c413780ddc8812797652a7dc29ba5ebcb/app/tools.py#L51-L58),
[V1 source](https://github.com/Zhaoyi-Fan/secure-llm-sdlc-reference/blob/v1.0.0/app/tools.py#L122-L142),
or the immutable
[`v0-vulnerable...v1.0.0` comparison](https://github.com/Zhaoyi-Fan/secure-llm-sdlc-reference/compare/v0-vulnerable...v1.0.0).

## Path B — manual V0/V1 HTTP comparison on Windows

This path starts both immutable snapshots locally and runs the same sanitized
HTTP checks against each. The driver logs in as fictional Alice, performs the
normal search, submits the fixed-marker `UNION SELECT` probe, checks literal `%`
behavior and prints no token or password hash.

### 1. Prepare the clone, Python environment and worktrees

```powershell
git clone https://github.com/Zhaoyi-Fan/secure-llm-sdlc-reference.git supportassist-case3
Set-Location .\supportassist-case3
git rev-parse "v0-vulnerable^{commit}"
git rev-parse "v1.0.0^{commit}"

py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

$main = (Get-Location).Path
$python = Join-Path $main ".venv\Scripts\python.exe"
$v0Lab = Join-Path (Split-Path $main -Parent) "supportassist-case3-v0"
$v1Lab = Join-Path (Split-Path $main -Parent) "supportassist-case3-v1"
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
$env:DB_PATH = Join-Path $v0Lab "case3-v0.db"
$env:JWT_SECRET = (& $python -c "import secrets; print(secrets.token_urlsafe(48))")
& $python -m app.seed
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

No Ollama or LM Studio process is needed for Case 3.

### 3. Reproduce V0

In terminal 2, opened in the `supportassist-case3` main clone:

```powershell
.\scripts\run_case_03_manual.ps1 -BaseUrl "http://127.0.0.1:8000" -Expected v0
```

Expected evidence:

```json
{
  "positive_control": {
    "returned_titles": ["Refund policy"]
  },
  "union_injection": {
    "injected_usernames": ["alice", "bob", "mallory"],
    "injected_row_count": 3
  },
  "like_metacharacter": {
    "query": "%",
    "result_count": 3
  },
  "expectation_met": true
}
```

The exact V0 fixture contains three KB articles, so the unescaped `%` matches
all three. The injected names prove that data from `users` crossed the intended
KB query boundary.

### 4. Start a fresh V1 API

Stop V0 with `Ctrl+C` in terminal 1. Then, still in terminal 1:

```powershell
Set-Location $v1Lab
$env:DB_PATH = Join-Path $v1Lab "case3-v1.db"
$env:JWT_SECRET = (& $python -c "import secrets; print(secrets.token_urlsafe(48))")
& $python -m app.seed
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 5. Verify V1 with the same checks

In terminal 2:

```powershell
.\scripts\run_case_03_manual.ps1 -BaseUrl "http://127.0.0.1:8000" -Expected v1
```

Expected evidence:

```json
{
  "positive_control": {
    "returned_titles": ["Refund policy"]
  },
  "union_injection": {
    "injected_usernames": [],
    "injected_row_count": 0
  },
  "like_metacharacter": {
    "query": "%",
    "result_count": 0
  },
  "expectation_met": true
}
```

The normal search still working is the positive control. Empty attack results
show that the payload remained data and that `%` was interpreted literally.

### 6. Cleanup

Stop V1 with `Ctrl+C`. In terminal 1, keep the resolved `$main`, `$v0Lab` and
`$v1Lab` values from setup and remove only the two named lab databases and the
two dedicated worktrees:

```powershell
Set-Location $main
Remove-Item -LiteralPath (Join-Path $v0Lab "case3-v0.db") -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $v1Lab "case3-v1.db") -ErrorAction SilentlyContinue
git worktree remove $v0Lab
git worktree remove $v1Lab
Remove-Item Env:DB_PATH -ErrorAction SilentlyContinue
Remove-Item Env:JWT_SECRET -ErrorAction SilentlyContinue
```

## Interpretation

Case 3 is not an LLM-specific vulnerability. It shows that an agent's retrieval
path remains ordinary application code: model-generated or user-supplied search
text must be bound as data, and search metacharacters need explicit semantics.

Continue with the detailed
[finding-to-fix record](findings/case-03-sql-injection.md).
