from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from app.agent import run_agent
from app.auth import validate_auth_config
from app.config import settings
from tests.providers import FinalAnswerProvider, MalformedProvider


def test_trace_is_opt_in(isolated_db, ids: dict[str, int]) -> None:
    del isolated_db
    result = run_agent(
        "Hello",
        ids["user:alice"],
        provider=FinalAnswerProvider(),
    )
    assert result == {"reply": "Safe final answer"}


def test_malformed_model_response_fails_closed(
    isolated_db,
    ids: dict[str, int],
) -> None:
    del isolated_db
    result = run_agent(
        "Hello",
        ids["user:alice"],
        provider=MalformedProvider(),
        include_trace=True,
    )
    assert result == {"reply": "(model response invalid)", "trace": []}


def test_short_signing_secret_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", "too-short")
    with pytest.raises(RuntimeError, match="at least 32 bytes"):
        validate_auth_config()


def test_expired_token_is_rejected(
    client: TestClient,
    ids: dict[str, int],
) -> None:
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(ids["user:alice"]),
            "username": "alice",
            "iat": now - timedelta(minutes=2),
            "exp": now - timedelta(minutes=1),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    response = client.get(
        "/orders",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
