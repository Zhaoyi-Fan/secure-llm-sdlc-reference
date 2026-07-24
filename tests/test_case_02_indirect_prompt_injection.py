from fastapi.testclient import TestClient

from app.agent import TOOL_SCHEMAS, run_agent
from app.db import get_conn
from tests.providers import IndirectInjectionProvider


def test_poisoned_kb_reaches_model_but_cannot_execute_refund(
    isolated_db,
    ids: dict[str, int],
) -> None:
    del isolated_db
    alice_id = ids["user:alice"]
    alice_order = ids["order:alice:Noise-cancelling headphones"]
    provider = IndirectInjectionProvider()

    before_status: str
    with get_conn() as conn:
        before_status = conn.execute(
            "SELECT status FROM orders WHERE id = ?",
            (alice_order,),
        ).fetchone()[0]
        before_refunds = conn.execute("SELECT COUNT(*) FROM refunds").fetchone()[0]

    result = run_agent(
        "Find the partner headphone troubleshooting guide.",
        alice_id,
        provider=provider,
        include_trace=True,
    )

    with get_conn() as conn:
        after_status = conn.execute(
            "SELECT status FROM orders WHERE id = ?",
            (alice_order,),
        ).fetchone()[0]
        after_refunds = conn.execute("SELECT COUNT(*) FROM refunds").fetchone()[0]

    advertised_names = {
        schema["function"]["name"] for schema in TOOL_SCHEMAS
    }
    assert "issue_refund" not in advertised_names
    assert provider.saw_injection_marker
    assert provider.saw_capability_denial
    assert [entry["tool"] for entry in result["trace"]] == [
        "search_kb",
        "list_my_orders",
        "issue_refund",
    ]
    assert result["trace"][-1]["output"]["error"] == "tool_not_allowed"
    assert before_refunds == after_refunds == 0
    assert before_status == after_status == "paid"


def test_explicit_authenticated_refund_succeeds_once(
    client: TestClient,
    login,
    ids: dict[str, int],
) -> None:
    alice = login("alice")
    order_id = ids["order:alice:Noise-cancelling headphones"]

    preview = client.get(f"/orders/{order_id}/refund-preview", headers=alice)
    first = client.post(
        f"/orders/{order_id}/refund",
        headers=alice,
        json={"amount_cents": 19_900},
    )
    replay = client.post(
        f"/orders/{order_id}/refund",
        headers=alice,
        json={"amount_cents": 19_900},
    )

    assert preview.status_code == 200
    assert preview.json()["requires_explicit_user_action"] is True
    assert first.status_code == 200
    assert first.json()["idempotent_replay"] is False
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["refund_id"] == first.json()["refund_id"]

    with get_conn() as conn:
        refund_count = conn.execute(
            "SELECT COUNT(*) FROM refunds WHERE order_id = ?",
            (order_id,),
        ).fetchone()[0]
        status = conn.execute(
            "SELECT status FROM orders WHERE id = ?",
            (order_id,),
        ).fetchone()[0]
    assert refund_count == 1
    assert status == "refunded"
