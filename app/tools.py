"""Agent tools.

Each function is also callable directly (bypassing the model) -- the HTTP API
layer and, later, the deterministic test suite drive these functions without
going through the LLM.
"""
from .db import get_conn


def list_my_orders(current_user_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, item, amount_cents, status, customer_note "
            "FROM orders WHERE user_id = ? ORDER BY id",
            (current_user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_order(order_id: int, current_user_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, user_id, item, amount_cents, status, customer_note "
            "FROM orders WHERE id = ?",
            (order_id,),
        ).fetchone()
    return dict(row) if row else None


def issue_refund(order_id: int, amount_cents: int, current_user_id: int) -> dict:
    with get_conn() as conn:
        order = conn.execute(
            "SELECT id, user_id, amount_cents, status FROM orders WHERE id = ?",
            (order_id,),
        ).fetchone()
        if order is None:
            return {"ok": False, "error": "order_not_found"}
        cur = conn.execute(
            "INSERT INTO refunds (order_id, amount_cents) VALUES (?, ?)",
            (order_id, amount_cents),
        )
        conn.execute("UPDATE orders SET status = 'refunded' WHERE id = ?", (order_id,))
    return {
        "ok": True,
        "refund_id": cur.lastrowid,
        "order_id": order_id,
        "amount_cents": amount_cents,
    }


def search_kb(query: str) -> list[dict]:
    sql = (
        "SELECT id, title, body FROM kb_articles "
        f"WHERE body LIKE '%{query}%' OR title LIKE '%{query}%'"
    )
    with get_conn() as conn:
        rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]
