import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import date, timedelta
from pathlib import Path

# In Docker this points at the mounted volume so the db survives the container.
DB_PATH = Path(os.environ.get("DB_PATH") or Path(__file__).resolve().parent.parent / "app.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS boards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS columns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    board_id INTEGER NOT NULL REFERENCES boards(id),
    column_key TEXT NOT NULL,
    title TEXT NOT NULL,
    position INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    column_id INTEGER NOT NULL REFERENCES columns(id),
    ticket_id TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    priority TEXT,
    assignee TEXT NOT NULL,
    due_date TEXT NOT NULL,
    progress INTEGER,
    position INTEGER NOT NULL
);
"""

# Same dummy cards as frontend/src/lib/seedData.ts, keyed by column.
SEED_COLUMNS = [
    ("backlog", "Backlog"),
    ("in-progress", "In Progress"),
    ("cab", "Change Review (CAB)"),
    ("deployed", "Deployed"),
]

SEED_CARDS = [
    ("TASK-1005", "Refresh firmware inventory spreadsheet", "Planning", None, "AS", 5, None, "backlog"),
    ("CHG-1090", "Decommission legacy VPN concentrator", "Network", "P2", "JR", 10, None, "backlog"),
    ("INC-2041", "Investigate intermittent Wi-Fi drops - Floor 3", "Incident", "P2", "MK", 1, None, "backlog"),
    ("CHG-1088", "Upgrade core switch firmware - DC2", "Network", "P1", "TL", 3, 65, "in-progress"),
    ("TASK-1002", "Rotate service account credentials", "Security", None, "AS", 2, 30, "in-progress"),
    ("INC-2038", "Resolve VPN authentication failures", "Incident", "P1", "JR", 0, 80, "in-progress"),
    ("CHG-1075", "Migrate DNS to new resolver cluster", "Network", "P2", "MK", 4, None, "cab"),
    ("CHG-1082", "Enable MFA enforcement org-wide", "Security", "P1", "TL", 6, None, "cab"),
    ("CHG-1050", "Patch edge firewalls - Q3 CVE batch", "Security", None, "JR", -2, None, "deployed"),
    ("CHG-1061", "Expand guest Wi-Fi capacity - HQ", "Network", None, "AS", -1, None, "deployed"),
    ("TASK-0998", "Decommission unused switch ports audit", "Planning", None, "MK", -12, None, "deployed"),
]


PBKDF2_ITERATIONS = 240_000
DEFAULT_USERNAME = "user"
DEFAULT_PASSWORD = "password"


def hash_password(password: str, salt: bytes | None = None) -> str:
    """Salted PBKDF2, stored as algorithm$iterations$salt$digest."""
    salt = secrets.token_bytes(16) if salt is None else salt
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    parts = stored.split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
        return False
    try:
        iterations, salt = int(parts[1]), bytes.fromhex(parts[2])
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return hmac.compare_digest(digest.hex(), parts[3])


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
        if _user_count(conn) == 0:
            _seed(conn)
        _upgrade_legacy_hashes(conn)
    finally:
        conn.close()


def _upgrade_legacy_hashes(conn: sqlite3.Connection) -> None:
    """Databases seeded before PBKDF2 hold a bare SHA-256 digest. Credentials
    are hardcoded for the MVP, so rehash in place rather than locking the user
    out of an existing volume."""
    rows = conn.execute("SELECT id, password_hash FROM users").fetchall()
    stale = [r["id"] for r in rows if not r["password_hash"].startswith("pbkdf2_sha256$")]
    for user_id in stale:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(DEFAULT_PASSWORD), user_id),
        )
    if stale:
        conn.commit()


def _user_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()
    return row["count"]


def _seed(conn: sqlite3.Connection) -> None:
    cur = conn.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (DEFAULT_USERNAME, hash_password(DEFAULT_PASSWORD)),
    )
    user_id = cur.lastrowid

    cur = conn.execute(
        "INSERT INTO boards (user_id, name) VALUES (?, ?)",
        (user_id, "Board"),
    )
    board_id = cur.lastrowid

    column_ids = {}
    for position, (key, title) in enumerate(SEED_COLUMNS):
        cur = conn.execute(
            "INSERT INTO columns (board_id, column_key, title, position) VALUES (?, ?, ?, ?)",
            (board_id, key, title, position),
        )
        column_ids[key] = cur.lastrowid

    today = date.today()
    column_positions = {key: 0 for key, _ in SEED_COLUMNS}
    for ticket_id, title, category, priority, assignee, offset, progress, column_key in SEED_CARDS:
        due_date = (today + timedelta(days=offset)).isoformat()
        position = column_positions[column_key]
        column_positions[column_key] += 1
        conn.execute(
            """
            INSERT INTO cards
                (column_id, ticket_id, title, category, priority, assignee, due_date, progress, position)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (column_ids[column_key], ticket_id, title, category, priority, assignee, due_date, progress, position),
        )

    conn.commit()
