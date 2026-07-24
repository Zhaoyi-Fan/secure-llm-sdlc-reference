import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from .config import settings


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection, commit on success, and always close it."""
    conn = sqlite3.connect(settings.db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id),
    item          TEXT NOT NULL,
    amount_cents  INTEGER NOT NULL CHECK (amount_cents > 0),
    status        TEXT NOT NULL DEFAULT 'paid'
                  CHECK (status IN ('paid', 'delivered', 'refunded')),
    customer_note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS refunds (
    id           INTEGER PRIMARY KEY,
    order_id     INTEGER NOT NULL REFERENCES orders(id),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (order_id)
);
CREATE TABLE IF NOT EXISTS kb_articles (
    id     INTEGER PRIMARY KEY,
    title  TEXT NOT NULL,
    body   TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'first_party'
           CHECK (source IN ('first_party', 'external_partner'))
);
"""


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)
