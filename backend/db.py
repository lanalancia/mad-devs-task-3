"""PostgreSQL access for poll entries and history."""

from __future__ import annotations

from datetime import datetime

import psycopg
from psycopg.rows import dict_row

from backend.config import load_config
from backend.urls import UrlError, normalize_url

POLL_ENTRY_COLUMNS = {
    "id",
    "url",
    "timeout_seconds",
    "interval_seconds",
    "expected_code",
    "status",
}
POLL_HISTORY_COLUMNS = {
    "id",
    "poll_entry_id",
    "polled_at",
    "http_status",
    "duration_ms",
    "message",
}
USER_COLUMNS = {
    "id",
    "username",
    "password",
}
REQUIRED_TABLES = {
    "poll_entries": POLL_ENTRY_COLUMNS,
    "poll_history": POLL_HISTORY_COLUMNS,
    "users": USER_COLUMNS,
}


class DatabaseError(Exception):
    """The database is unreachable or the application tables are not usable."""


def connect() -> psycopg.Connection:
    config = load_config()
    try:
        port = int(config["port"])
    except ValueError as exc:
        raise DatabaseError(f"Port in config.ini is not a number: {config['port']}") from exc
    try:
        return psycopg.connect(
            host=config["host"],
            port=port,
            dbname=config["database"],
            user=config["user"],
            password=config["password"],
            connect_timeout=5,
            row_factory=dict_row,
            autocommit=True,
        )
    except psycopg.Error as exc:
        raise DatabaseError(" ".join(str(exc).split())) from exc


def ensure_schema(connection: psycopg.Connection) -> None:
    """Exit path for a missing or unexpected application schema."""
    problems: list[str] = []
    for table_name, required in REQUIRED_TABLES.items():
        present = _columns(connection, table_name)
        if not present:
            problems.append(f"Table {table_name} is missing.")
            continue
        missing = sorted(required - present)
        if missing:
            joined = ", ".join(missing)
            problems.append(f"Table {table_name} has the wrong format. Missing columns: {joined}.")
    if problems:
        detail = " ".join(problems)
        raise DatabaseError(
            f"{detail} Run python install.py and choose the Docker PostgreSQL install."
        )
    _ensure_deleted_status(connection)
    _ensure_events_table(connection)
    _ensure_groups(connection)
    _normalize_stored_urls(connection)


def _ensure_deleted_status(connection: psycopg.Connection) -> None:
    """Allow the soft-delete status on databases created before it existed."""
    row = connection.execute(
        """
        SELECT pg_get_constraintdef(oid) AS definition
        FROM pg_constraint
        WHERE conrelid = 'public.poll_entries'::regclass
          AND conname = 'poll_entries_status_check'
        """
    ).fetchone()
    if row is not None and "DELETED" in row["definition"]:
        return
    if row is not None:
        connection.execute(
            "ALTER TABLE poll_entries DROP CONSTRAINT poll_entries_status_check"
        )
    connection.execute(
        """
        ALTER TABLE poll_entries
        ADD CONSTRAINT poll_entries_status_check
        CHECK (status IN ('ACTIVE', 'PAUSED', 'DELETED'))
        """
    )


def _ensure_events_table(connection: psycopg.Connection) -> None:
    """Add the pause and delete log on databases created before it existed."""
    if _columns(connection, "poll_entry_events"):
        return
    connection.execute(
        """
        CREATE TABLE poll_entry_events (
            id bigserial PRIMARY KEY,
            poll_entry_id bigint NOT NULL REFERENCES poll_entries (id) ON DELETE CASCADE,
            kind text NOT NULL CHECK (kind IN ('paused', 'resumed', 'deleted', 'restored')),
            happened_at timestamptz NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX poll_entry_events_entry_happened_at_idx
            ON poll_entry_events (poll_entry_id, happened_at)
        """
    )


def _ensure_groups(connection: psycopg.Connection) -> None:
    """Add groups on databases created before they existed."""
    if not _columns(connection, "poll_groups"):
        connection.execute(
            """
            CREATE TABLE poll_groups (
                id bigserial PRIMARY KEY,
                name text NOT NULL UNIQUE CHECK (char_length(name) BETWEEN 1 AND 50),
                paused boolean NOT NULL DEFAULT false
            )
            """
        )
    if not _columns(connection, "poll_group_emails"):
        connection.execute(
            """
            CREATE TABLE poll_group_emails (
                id bigserial PRIMARY KEY,
                poll_group_id bigint NOT NULL REFERENCES poll_groups (id) ON DELETE CASCADE,
                address text NOT NULL,
                UNIQUE (poll_group_id, address)
            )
            """
        )
    if "group_id" not in _columns(connection, "poll_entries"):
        connection.execute(
            """
            ALTER TABLE poll_entries
            ADD COLUMN group_id bigint REFERENCES poll_groups (id) ON DELETE SET NULL
            """
        )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS poll_entries_group_id_idx
            ON poll_entries (group_id)
        """
    )


def _normalize_stored_urls(connection: psycopg.Connection) -> None:
    """Rewrite saved addresses into the same form new entries use."""
    rows = connection.execute("SELECT id, url FROM poll_entries").fetchall()
    for row in rows:
        try:
            normalized = normalize_url(row["url"])
        except UrlError:
            continue
        if normalized == row["url"]:
            continue
        try:
            with connection.transaction():
                connection.execute(
                    "UPDATE poll_entries SET url = %s WHERE id = %s",
                    (normalized, row["id"]),
                )
        except psycopg.errors.UniqueViolation:
            print(f"Left {row['url']} unchanged: {normalized} already exists.")


def load_active_entries(connection: psycopg.Connection) -> list[dict]:
    return connection.execute(
        """
        SELECT
            poll_entries.id,
            poll_entries.url,
            poll_entries.timeout_seconds,
            poll_entries.interval_seconds,
            poll_entries.expected_code,
            MAX(poll_history.polled_at) AS last_polled_at
        FROM poll_entries
        LEFT JOIN poll_history ON poll_history.poll_entry_id = poll_entries.id
        LEFT JOIN poll_groups ON poll_groups.id = poll_entries.group_id
        WHERE poll_entries.status = 'ACTIVE'
          AND COALESCE(poll_groups.paused, false) = false
        GROUP BY poll_entries.id
        ORDER BY poll_entries.id
        """
    ).fetchall()


def insert_history(
    connection: psycopg.Connection,
    poll_entry_id: int,
    polled_at: datetime,
    http_status: int | None,
    duration_ms: int,
    message: str,
) -> None:
    connection.execute(
        """
        INSERT INTO poll_history (
            poll_entry_id,
            polled_at,
            http_status,
            duration_ms,
            message
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (poll_entry_id, polled_at, http_status, duration_ms, message),
    )


def _columns(connection: psycopg.Connection, table_name: str) -> set[str]:
    rows = connection.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table_name,),
    ).fetchall()
    return {row["column_name"] for row in rows}
