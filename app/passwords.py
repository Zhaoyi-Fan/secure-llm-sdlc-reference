"""Password hashing helpers (stdlib only)."""
import hashlib
import hmac
import os


def make_salt() -> str:
    return os.urandom(16).hex()


def hash_password(password: str, salt: str) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000)
    return dk.hex()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_password(password, salt), expected_hash)
