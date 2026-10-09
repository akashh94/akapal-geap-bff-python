"""The user_id -> agent session_id mapping (ADK_SESSION_AND_BFF.md §4.1).

The BFF owns the pointer; the agent owns the conversation. SQLite via the
stdlib, one connection per operation (small local DB, no pool needed).
"""

import os
import sqlite3
from datetime import datetime, timezone

from .config import DATABASE_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_threads (
  user_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  PRIMARY KEY (user_id, session_id)
);
"""


def _connect() -> sqlite3.Connection:
    parent = os.path.dirname(DATABASE_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_active_thread(user_id: str) -> str | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT session_id FROM chat_threads WHERE user_id = ?"
            " ORDER BY last_seen_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    return row["session_id"] if row else None


def owns_thread(user_id: str, session_id: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM chat_threads WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        ).fetchone()
    return row is not None


def save_thread(user_id: str, session_id: str) -> None:
    now = _now()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO chat_threads (user_id, session_id, created_at, last_seen_at)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT(user_id, session_id)"
            " DO UPDATE SET last_seen_at = excluded.last_seen_at",
            (user_id, session_id, now, now),
        )
