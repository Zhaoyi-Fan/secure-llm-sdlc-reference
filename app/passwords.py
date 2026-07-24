"""Password hashing helpers (stdlib only)."""
import hashlib
import hmac
import os

PBKDF2_ITERATIONS = 600_000


def make_salt() -> str:
    return os.urandom(16).hex()


def hash_password(password: str, salt: str) -> str:
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        bytes.fromhex(salt),
        PBKDF2_ITERATIONS,
    )
    return dk.hex()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_password(password, salt), expected_hash)
