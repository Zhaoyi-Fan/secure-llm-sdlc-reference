import shutil
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_conn
from app.main import app
from app.seed import seed

TEST_JWT_SECRET = "test-only-" + ("a" * 64)


@pytest.fixture(scope="session")
def seeded_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    template = tmp_path_factory.mktemp("supportassist-template") / "seeded.db"
    original_path = settings.db_path
    original_secret = settings.jwt_secret
    try:
        settings.db_path = str(template)
        settings.jwt_secret = TEST_JWT_SECRET
        seed(reset=True)
    finally:
        settings.db_path = original_path
        settings.jwt_secret = original_secret
    return template


@pytest.fixture
def isolated_db(
    tmp_path: Path,
    seeded_template: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    database = tmp_path / "supportassist-test.db"
    shutil.copyfile(seeded_template, database)
    monkeypatch.setattr(settings, "db_path", str(database))
    monkeypatch.setattr(settings, "jwt_secret", TEST_JWT_SECRET)
    monkeypatch.setattr(settings, "jwt_ttl_seconds", 900)
    monkeypatch.setattr(settings, "expose_debug_trace", False)
    return database


@pytest.fixture
def client(isolated_db: Path) -> Iterator[TestClient]:
    del isolated_db
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def login(client: TestClient) -> Callable[[str], dict[str, str]]:
    def _login(username: str) -> dict[str, str]:
        response = client.post(
            "/login",
            json={"username": username, "password": f"{username}-password"},
        )
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login


@pytest.fixture
def ids(isolated_db: Path) -> dict[str, int]:
    del isolated_db
    with get_conn() as conn:
        user_rows = conn.execute("SELECT id, username FROM users").fetchall()
        order_rows = conn.execute(
            "SELECT orders.id, users.username, orders.item "
            "FROM orders JOIN users ON users.id = orders.user_id"
        ).fetchall()
    result = {f"user:{row['username']}": row["id"] for row in user_rows}
    result.update(
        {
            f"order:{row['username']}:{row['item']}": row["id"]
            for row in order_rows
        }
    )
    return result
