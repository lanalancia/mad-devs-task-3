"""PostgreSQL access for poll entries and history."""

from __future__ import annotations

from datetime import datetime

import psycopg
from psycopg.rows import dict_row

from backend.config import load_config

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
REQUIRED_TABLES = {
    "poll_entries": POLL_ENTRY_COLUMNS,
    "poll_history": POLL_HISTORY_COLUMNS,
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
    """Exit path for a missing or unexpected poll schema.

    The users table is created by install.py and is not read here.
    """
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
        WHERE poll_entries.status = 'ACTIVE'
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
