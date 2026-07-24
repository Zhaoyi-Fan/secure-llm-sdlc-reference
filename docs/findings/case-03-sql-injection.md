# Case 03 — SQL injection in knowledge-base search

## Risk

**High.** An authenticated user could change the structure of the KB query and
union data from other tables into the result. In the local baseline, this can
expose fictional usernames and password hashes.

Mappings: CWE-89 and OWASP Top 10 A05:2025 (Injection).

## Preconditions and affected assets

- The attacker has a valid customer account.
- The attacker controls the KB `q` parameter.
- Affected assets: database confidentiality and query integrity.

## Vulnerable evidence

Historical snapshot: `v0-vulnerable` at commit `64924b3`.

`search_kb` embeds the query in an f-string. A column-compatible `UNION SELECT`
input returns rows that a normal KB search cannot produce.

## Root cause

Untrusted input was used as SQL syntax instead of being bound as a value.
Simple string filtering would not provide a reliable grammar boundary.

## Fix

- Both `LIKE` patterns use SQLite bound parameters.
- Backslash, `%` and `_` are escaped so search metacharacters are treated
  literally.
- Query length is limited at both HTTP and tool boundaries.
- Results are capped at ten articles.

## Verification

`tests/test_case_03_sql_injection.py` proves:

- a column-compatible union payload returns no injected rows;
- normal title search still returns the intended article;
- a standalone `%` is treated literally instead of matching every article.

## Residual risk

Parameter binding addresses this query. New dynamic sorting, filtering,
reporting or migration code must avoid constructing identifiers or clauses from
untrusted strings. Production data access would also require monitoring and
least-privilege database credentials.
