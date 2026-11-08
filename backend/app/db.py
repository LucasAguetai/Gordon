"""Stockage SQLite.

Trois choses à persister :
  - les passkeys enregistrées (credentials WebAuthn)
  - l'utilisateur unique propriétaire de l'instance
  - l'identifiant de session Claude par (utilisateur, agent), pour que chaque
    agent retrouve le fil de la conversation après un redémarrage
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS credentials (
    credential_id TEXT PRIMARY KEY,   -- base64url
    user_id       TEXT NOT NULL REFERENCES users(id),
    public_key    BLOB NOT NULL,
    sign_count    INTEGER NOT NULL DEFAULT 0,
    transports    TEXT,
    label         TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agent_sessions (
    user_id    TEXT NOT NULL,
    agent_id   TEXT NOT NULL,
    session_id TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, agent_id)
);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


# --- Utilisateurs ---------------------------------------------------------


def create_user(user_id: str, label: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, label) VALUES (?, ?)",
            (user_id, label),
        )


def get_user(user_id: str) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()


def user_count() -> int:
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]


# --- Passkeys ------------------------------------------------------------


def add_credential(
    credential_id: str,
    user_id: str,
    public_key: bytes,
    sign_count: int,
    transports: str | None,
    label: str | None,
) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO credentials
               (credential_id, user_id, public_key, sign_count, transports, label)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (credential_id, user_id, public_key, sign_count, transports, label),
        )


def get_credential(credential_id: str) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM credentials WHERE credential_id = ?", (credential_id,)
        ).fetchone()


def list_credentials(user_id: str) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM credentials WHERE user_id = ?", (user_id,)
        ).fetchall()


def credential_count() -> int:
    with connect() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM credentials"
        ).fetchone()["n"]


def update_sign_count(credential_id: str, sign_count: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE credentials SET sign_count = ? WHERE credential_id = ?",
            (sign_count, credential_id),
        )


def delete_credential(credential_id: str, user_id: str) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM credentials WHERE credential_id = ? AND user_id = ?",
            (credential_id, user_id),
        )
        return cur.rowcount > 0


# --- Sessions d'agents ---------------------------------------------------


def get_agent_session(user_id: str, agent_id: str) -> str | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT session_id FROM agent_sessions WHERE user_id = ? AND agent_id = ?",
            (user_id, agent_id),
        ).fetchone()
        return row["session_id"] if row else None


def set_agent_session(user_id: str, agent_id: str, session_id: str) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO agent_sessions (user_id, agent_id, session_id, updated_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(user_id, agent_id)
               DO UPDATE SET session_id = excluded.session_id,
                             updated_at = datetime('now')""",
            (user_id, agent_id, session_id),
        )


def clear_agent_session(user_id: str, agent_id: str) -> None:
    with connect() as conn:
        conn.execute(
            "DELETE FROM agent_sessions WHERE user_id = ? AND agent_id = ?",
            (user_id, agent_id),
        )
