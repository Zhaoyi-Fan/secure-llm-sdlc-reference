import jwt

from .config import settings
from .db import get_conn
from .passwords import verify_password


def create_token(user_id: int, username: str) -> str:
    payload = {"sub": str(user_id), "username": username}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def authenticate(username: str, password: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, salt FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if row is None:
        return None
    if not verify_password(password, row["salt"], row["password_hash"]):
        return None
    return {"id": row["id"], "username": row["username"]}
