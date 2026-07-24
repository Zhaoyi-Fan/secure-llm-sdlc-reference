"""Create and seed the demo database with fictional users, orders and KB articles."""
from .db import get_conn, init_db
from .passwords import hash_password, make_salt

# (username, password) -- demo credentials only.
USERS = [
    ("alice", "alice-password"),
    ("bob", "bob-password"),
    ("mallory", "mallory-password"),
]

# (username, item, amount_cents, status)
ORDERS = [
    ("alice", "Noise-cancelling headphones", 19900, "paid"),
    ("alice", "USB-C cable", 1200, "paid"),
    ("bob", "Mechanical keyboard", 8900, "paid"),
    ("bob", "Laptop stand", 4500, "delivered"),
    ("mallory", "Webcam", 5900, "paid"),
]

# (title, body)
KB = [
    ("Refund policy", "Customers may request a refund within 30 days of purchase for items in original condition."),
    ("Shipping times", "Standard shipping takes 3-5 business days. Express shipping takes 1-2 business days."),
    ("Damaged items", "If an item arrives damaged, contact support with your order number and a photo of the damage."),
]


def seed(reset: bool = True) -> None:
    init_db()
    with get_conn() as conn:
        if reset:
            conn.executescript(
                "DELETE FROM refunds; DELETE FROM orders; "
                "DELETE FROM kb_articles; DELETE FROM users;"
            )
        user_ids: dict[str, int] = {}
        for username, password in USERS:
            salt = make_salt()
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
                (username, hash_password(password, salt), salt),
            )
            user_ids[username] = cur.lastrowid
        for username, item, amount, status in ORDERS:
            conn.execute(
                "INSERT INTO orders (user_id, item, amount_cents, status) VALUES (?, ?, ?, ?)",
                (user_ids[username], item, amount, status),
            )
        for title, body in KB:
            conn.execute("INSERT INTO kb_articles (title, body) VALUES (?, ?)", (title, body))


if __name__ == "__main__":
    seed()
    print("Seeded SupportAssist database.")
