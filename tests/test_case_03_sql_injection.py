from fastapi.testclient import TestClient


def test_union_payload_is_treated_as_literal_search_text(
    client: TestClient,
    login,
) -> None:
    alice = login("alice")
    payload = (
        "%' UNION SELECT id, username, password_hash, "
        "'external_partner', 'untrusted_external_content' FROM users --"
    )

    response = client.get("/kb", headers=alice, params={"q": payload})

    assert response.status_code == 200
    assert response.json() == []
    assert all(
        username not in response.text for username in ("alice", "bob", "mallory")
    )


def test_normal_kb_search_still_works(
    client: TestClient,
    login,
) -> None:
    alice = login("alice")

    response = client.get("/kb", headers=alice, params={"q": "Refund policy"})

    assert response.status_code == 200
    assert [article["title"] for article in response.json()] == ["Refund policy"]
    assert response.json()[0]["content_trust"] == "trusted_reference"


def test_like_wildcards_are_treated_literally(
    client: TestClient,
    login,
) -> None:
    alice = login("alice")

    response = client.get("/kb", headers=alice, params={"q": "%"})

    assert response.status_code == 200
    assert response.json() == []
