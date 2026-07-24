from fastapi.testclient import TestClient

from app.db import get_conn


def test_customer_can_read_own_order_but_not_another_customers(
    client: TestClient,
    login,
    ids: dict[str, int],
) -> None:
    alice = login("alice")
    alice_order = ids["order:alice:Noise-cancelling headphones"]
    bob_order = ids["order:bob:Mechanical keyboard"]

    own_response = client.get(f"/orders/{alice_order}", headers=alice)
    other_response = client.get(f"/orders/{bob_order}", headers=alice)

    assert own_response.status_code == 200
    assert own_response.json()["item"] == "Noise-cancelling headphones"
    assert "user_id" not in own_response.json()
    assert other_response.status_code == 404


def test_customer_cannot_refund_another_customers_order(
    client: TestClient,
    login,
    ids: dict[str, int],
) -> None:
    alice = login("alice")
    bob_order = ids["order:bob:Mechanical keyboard"]

    response = client.post(
        f"/orders/{bob_order}/refund",
        headers=alice,
        json={"amount_cents": 8_900},
    )

    assert response.status_code == 404
    with get_conn() as conn:
        refund_count = conn.execute(
            "SELECT COUNT(*) FROM refunds WHERE order_id = ?",
            (bob_order,),
        ).fetchone()[0]
        status = conn.execute(
            "SELECT status FROM orders WHERE id = ?",
            (bob_order,),
        ).fetchone()[0]
    assert refund_count == 0
    assert status == "paid"


def test_server_rejects_negative_and_non_full_refunds(
    client: TestClient,
    login,
    ids: dict[str, int],
) -> None:
    alice = login("alice")
    order_id = ids["order:alice:Noise-cancelling headphones"]

    negative = client.post(
        f"/orders/{order_id}/refund",
        headers=alice,
        json={"amount_cents": -1},
    )
    excessive = client.post(
        f"/orders/{order_id}/refund",
        headers=alice,
        json={"amount_cents": 999_999},
    )

    assert negative.status_code == 422
    assert excessive.status_code == 422
    with get_conn() as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM refunds WHERE order_id = ?",
                (order_id,),
            ).fetchone()[0]
            == 0
        )
