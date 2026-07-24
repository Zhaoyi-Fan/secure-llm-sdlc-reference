"""Server-side capabilities used by the HTTP API and the LLM agent.

The authenticated principal is always supplied by trusted application code.
Model-provided arguments are treated as untrusted input.
"""

from .db import get_conn

REFUNDABLE_STATUSES = {"paid", "delivered"}


def list_my_orders(current_user_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, item, amount_cents, status, customer_note "
            "FROM orders WHERE user_id = ? ORDER BY id",
            (current_user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_order(order_id: int, current_user_id: int) -> dict | None:
    """Return an order only when it belongs to the authenticated principal."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, item, amount_cents, status, customer_note "
            "FROM orders WHERE id = ? AND user_id = ?",
            (order_id, current_user_id),
        ).fetchone()
    return dict(row) if row else None


def prepare_refund(order_id: int, current_user_id: int) -> dict:
    """Return a read-only refund preview; this capability never moves money."""
    with get_conn() as conn:
        order = conn.execute(
            "SELECT id, amount_cents, status FROM orders "
            "WHERE id = ? AND user_id = ?",
            (order_id, current_user_id),
        ).fetchone()
        existing = conn.execute(
            "SELECT id, amount_cents FROM refunds WHERE order_id = ?",
            (order_id,),
        ).fetchone()

    if order is None:
        return {"ok": False, "error": "order_not_found"}
    if existing is not None or order["status"] == "refunded":
        return {"ok": False, "error": "already_refunded"}
    if order["status"] not in REFUNDABLE_STATUSES:
        return {"ok": False, "error": "order_not_refundable"}
    return {
        "ok": True,
        "order_id": order["id"],
        "amount_cents": order["amount_cents"],
        "requires_explicit_user_action": True,
    }


def issue_refund(order_id: int, amount_cents: int, current_user_id: int) -> dict:
    """Execute an authenticated, full-order refund outside the LLM tool set.

    An immediate transaction plus the unique order constraint makes repeated or
    concurrent calls idempotent at the order resource boundary.
    """
    if amount_cents <= 0:
        return {"ok": False, "error": "invalid_amount"}

    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        order = conn.execute(
            "SELECT id, amount_cents, status FROM orders "
            "WHERE id = ? AND user_id = ?",
            (order_id, current_user_id),
        ).fetchone()
        if order is None:
            return {"ok": False, "error": "order_not_found"}

        existing = conn.execute(
            "SELECT id, amount_cents FROM refunds WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        if existing is not None:
            if existing["amount_cents"] == amount_cents:
                return {
                    "ok": True,
                    "refund_id": existing["id"],
                    "order_id": order_id,
                    "amount_cents": existing["amount_cents"],
                    "idempotent_replay": True,
                }
            return {"ok": False, "error": "already_refunded"}

        if order["status"] not in REFUNDABLE_STATUSES:
            return {"ok": False, "error": "order_not_refundable"}
        if amount_cents != order["amount_cents"]:
            return {
                "ok": False,
                "error": "amount_must_equal_order_total",
                "expected_amount_cents": order["amount_cents"],
            }

        cursor = conn.execute(
            "INSERT INTO refunds (order_id, amount_cents) VALUES (?, ?)",
            (order_id, amount_cents),
        )
        conn.execute(
            "UPDATE orders SET status = 'refunded' "
            "WHERE id = ? AND user_id = ?",
            (order_id, current_user_id),
        )

    return {
        "ok": True,
        "refund_id": cursor.lastrowid,
        "order_id": order_id,
        "amount_cents": amount_cents,
        "idempotent_replay": False,
    }


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_kb(query: str) -> list[dict]:
    """Search KB text with a bound, literal LIKE pattern."""
    if not query or len(query) > 200:
        return []
    pattern = f"%{_escape_like(query)}%"
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, body, source, "
            "CASE WHEN source = 'first_party' "
            "THEN 'trusted_reference' ELSE 'untrusted_external_content' END "
            "AS content_trust "
            "FROM kb_articles "
            "WHERE body LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\' "
            "ORDER BY id LIMIT 10",
            (pattern, pattern),
        ).fetchall()
    return [dict(row) for row in rows]
