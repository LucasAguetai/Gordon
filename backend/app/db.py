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

CREATE TABLE IF NOT EXISTS agents (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    role            TEXT NOT NULL,
    tagline         TEXT NOT NULL,
    accent          TEXT NOT NULL,
    tools           TEXT NOT NULL,   -- tableau JSON
    system_prompt   TEXT NOT NULL,
    look            TEXT NOT NULL,   -- objet JSON décrivant l'avatar
    effort          TEXT,
    needs_workspace INTEGER NOT NULL DEFAULT 0,
    workspace       TEXT,            -- dossier de travail, si outils fichiers
    position        INTEGER NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Colonnes ajoutées après coup. CREATE TABLE IF NOT EXISTS ne touche pas une
# table déjà créée : sans ça, une base existante garderait l'ancien schéma.
MIGRATIONS: list[tuple[str, str]] = [
    ("agents", "workspace TEXT"),
]


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

        for table, definition in MIGRATIONS:
            column = definition.split()[0]
            existing = {
                row["name"]
                for row in conn.execute(f"PRAGMA table_info({table})")
            }
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


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


# --- Agents ---------------------------------------------------------------


def list_agents() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM agents ORDER BY position, created_at"
        ).fetchall()


def get_agent(agent_id: str) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()


def agent_count() -> int:
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM agents").fetchone()["n"]


def next_position() -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(position), 0) + 1 AS n FROM agents"
        ).fetchone()
        return row["n"]


def insert_agent(**fields) -> None:
    columns = ", ".join(fields)
    holders = ", ".join("?" for _ in fields)
    with connect() as conn:
        conn.execute(
            f"INSERT INTO agents ({columns}) VALUES ({holders})",
            tuple(fields.values()),
        )


def update_agent_workspace(
    agent_id: str, *, needs_workspace: int, workspace: str | None
) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE agents SET needs_workspace = ?, workspace = ? WHERE id = ?",
            (needs_workspace, workspace, agent_id),
        )


def delete_agent(agent_id: str) -> bool:
    """Supprime un agent et le fil de conversation qui lui est rattaché.

    Sans le second DELETE, recréer un agent sous le même identifiant
    reprendrait la conversation du précédent.
    """
    with connect() as conn:
        cur = conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        conn.execute("DELETE FROM agent_sessions WHERE agent_id = ?", (agent_id,))
        return cur.rowcount > 0
