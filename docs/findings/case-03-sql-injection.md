# Case 03 — SQL injection in knowledge-base search

**Layer:** conventional data/API AppSec in an LLM-enabled application. The
vulnerable `/kb` route can be exploited directly without a model, and the same
parameterized-query rule must also protect agent retrieval tools.

## Risk

**High.** An authenticated user could change the structure of the KB query and
union data from other tables into the result. The public local-lab proof
extracts only fictional usernames plus a fixed marker; the primitive is not
limited to those columns.

Mappings: CWE-89 and OWASP Top 10 A05:2025 (Injection).

## Preconditions and affected assets

- The attacker has a valid customer account.
- The attacker controls the KB `q` parameter.
- Affected assets: database confidentiality and query integrity.

## Vulnerable evidence

Historical snapshot: `v0-vulnerable` at commit `64924b3`.

`search_kb` embeds the query in an f-string. A column-compatible `UNION SELECT`
input returns rows that a normal KB search cannot produce.

```python
# v0-vulnerable
sql = (
    "SELECT id, title, body FROM kb_articles "
    f"WHERE body LIKE '%{query}%' OR title LIKE '%{query}%'"
)
conn.execute(sql)
```

Because `query` becomes SQL syntax, a payload can terminate the `LIKE` value
and add another query. See the immutable
[`search_kb` V0 source](https://github.com/Zhaoyi-Fan/secure-llm-sdlc-reference/blob/64924b3c413780ddc8812797652a7dc29ba5ebcb/app/tools.py#L51-L58).

## Root cause

Untrusted input was used as SQL syntax instead of being bound as a value.
Simple string filtering would not provide a reliable grammar boundary.

## Fix

- Both `LIKE` patterns use SQLite bound parameters.
- Backslash, `%` and `_` are escaped so search metacharacters are treated
  literally.
- Query length is limited at both HTTP and tool boundaries.
- Results are capped at ten articles.

```python
# v1.0.0 / hardened main
pattern = f"%{_escape_like(query)}%"
rows = conn.execute(
    "... WHERE body LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\' ...",
    (pattern, pattern),
).fetchall()
```

Parameter binding is the SQL-injection boundary: the driver treats the payload
as a value rather than executable SQL. `_escape_like` is a separate semantic
control that makes `%` and `_` literal search characters. This is a
parameterized query; the finding does not depend on claiming a separately
managed server-side prepared statement. See the immutable
[`search_kb` V1 source](https://github.com/Zhaoyi-Fan/secure-llm-sdlc-reference/blob/v1.0.0/app/tools.py#L122-L142)
and the
[`v0-vulnerable...v1.0.0` comparison](https://github.com/Zhaoyi-Fan/secure-llm-sdlc-reference/compare/v0-vulnerable...v1.0.0).

## Verification

[`tests/test_case_03_sql_injection.py`](../../tests/test_case_03_sql_injection.py)
proves:

- a column-compatible union payload returns no injected rows;
- normal title search still returns the intended article;
- a standalone `%` is treated literally instead of matching every article.

The payload uses a fixed `CASE3_INJECTED_ROW` value and never requests a
password hash. For a safe automated replay and an optional loopback-only manual
comparison, follow the [Case 3 guided lab](../case-03-lab.md).

## Residual risk

Parameter binding addresses this query. New dynamic sorting, filtering,
reporting or migration code must avoid constructing identifiers or clauses from
untrusted strings. Production data access would also require monitoring and
least-privilege database credentials.
