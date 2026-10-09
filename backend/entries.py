"""Visible poll entries: one page at a time, soft-deleted rows excluded."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import psycopg

from backend.auth import passwords_match

PAGE_SIZES = (10, 25, 50, 100)
DEFAULT_EXPECTED_CODE = 200


class EntryError(Exception):
    """The requested change cannot be applied."""


def creation_action(status: str | None) -> str:
    """How a filled URL is saved: create, restore, or exists."""
    if status is None:
        return "create"
    if status == "DELETED":
        return "restore"
    return "exists"


def health_fields(message: str | None) -> tuple[str, str]:
    """Status column and error column for the latest history row."""
    if message is None:
        return "", ""
    if message == "OK":
        return "UP", ""
    return "DOWN", message


def clamp_page(page: int, page_size: int, total: int) -> int:
    page_count = max(1, (total + page_size - 1) // page_size) if total else 1
    if page < 1:
        return 1
    if page > page_count:
        return page_count
    return page


def require_page(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise EntryError("Page must be an integer of at least 1.")
    return value


def require_page_size(value: object) -> int:
    if value not in PAGE_SIZES:
        raise EntryError("Page size must be 10, 25, 50, or 100.")
    return int(value)


def require_seconds(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise EntryError(f"{label} must be an integer of at least 1.")
    return value


def require_url(value: object) -> str:
    if not isinstance(value, str):
        raise EntryError("URL must be a string.")
    url = value.strip()
    if not url:
        raise EntryError("URL is required.")
    return url


def require_poll_status(value: object) -> str:
    if value not in {"ACTIVE", "PAUSED"}:
        raise EntryError("Status must be ACTIVE or PAUSED.")
    return str(value)


def load_page(connection: psycopg.Connection, page: int, page_size: int) -> dict:
    with connection.transaction():
        total = connection.execute(
            "SELECT COUNT(*) AS total FROM poll_entries WHERE status <> 'DELETED'"
        ).fetchone()["total"]
        page = clamp_page(page, page_size, total)
        offset = (page - 1) * page_size
        rows = connection.execute(
            """
            SELECT
                poll_entries.id,
                poll_entries.url,
                poll_entries.timeout_seconds,
                poll_entries.interval_seconds,
                poll_entries.status,
                latest.polled_at AS last_polled_at,
                latest.message AS last_message
            FROM poll_entries
            LEFT JOIN LATERAL (
                SELECT polled_at, message
                FROM poll_history
                WHERE poll_history.poll_entry_id = poll_entries.id
                ORDER BY polled_at DESC, poll_history.id DESC
                LIMIT 1
            ) AS latest ON TRUE
            WHERE poll_entries.status <> 'DELETED'
            ORDER BY poll_entries.id
            LIMIT %s OFFSET %s
            """,
            (page_size, offset),
        ).fetchall()
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "entries": [_serialize(row) for row in rows],
    }


def authenticate(connection: psycopg.Connection, username: str, password: str) -> str | None:
    if not isinstance(username, str) or not isinstance(password, str):
        return None
    row = connection.execute(
        "SELECT username, password FROM users WHERE username = %s",
        (username,),
    ).fetchone()
    if row is None or not passwords_match(password, row["password"]):
        return None
    return row["username"]


def save_new_entry(
    connection: psycopg.Connection,
    url: str,
    interval_seconds: int,
    timeout_seconds: int,
    page: int,
    page_size: int,
) -> tuple[str, dict | None]:
    """Create or restore a URL. exists means the caller should reject it."""
    try:
        with connection.transaction():
            existing = connection.execute(
                "SELECT status FROM poll_entries WHERE url = %s",
                (url,),
            ).fetchone()
            action = creation_action(None if existing is None else existing["status"])
            if action == "exists":
                return "exists", None
            if action == "create":
                connection.execute(
                    """
                    INSERT INTO poll_entries (
                        url, timeout_seconds, interval_seconds, expected_code, status
                    )
                    VALUES (%s, %s, %s, %s, 'PAUSED')
                    """,
                    (url, timeout_seconds, interval_seconds, DEFAULT_EXPECTED_CODE),
                )
            else:
                updated = connection.execute(
                    """
                    UPDATE poll_entries
                    SET timeout_seconds = %s,
                        interval_seconds = %s,
                        status = 'PAUSED'
                    WHERE url = %s AND status = 'DELETED'
                    """,
                    (timeout_seconds, interval_seconds, url),
                )
                if updated.rowcount != 1:
                    return "exists", None
    except psycopg.errors.UniqueViolation:
        return "exists", None
    return action, load_page(connection, page, page_size)


def update_entry(
    connection: psycopg.Connection,
    url: str,
    interval_seconds: int,
    timeout_seconds: int,
    status: str,
    page: int,
    page_size: int,
) -> dict | None:
    updated = connection.execute(
        """
        UPDATE poll_entries
        SET interval_seconds = %s,
            timeout_seconds = %s,
            status = %s
        WHERE url = %s AND status <> 'DELETED'
        """,
        (interval_seconds, timeout_seconds, status, url),
    )
    if updated.rowcount != 1:
        return None
    return load_page(connection, page, page_size)


def delete_entry(
    connection: psycopg.Connection,
    url: str,
    page: int,
    page_size: int,
) -> dict | None:
    updated = connection.execute(
        """
        UPDATE poll_entries
        SET status = 'DELETED'
        WHERE url = %s AND status <> 'DELETED'
        """,
        (url,),
    )
    if updated.rowcount != 1:
        return None
    return load_page(connection, page, page_size)


def _serialize(row: dict) -> dict:
    health, error = health_fields(row["last_message"])
    last_polled_at = _aware(row["last_polled_at"])
    next_poll_at = None
    if last_polled_at is not None:
        next_poll_at = last_polled_at + timedelta(seconds=row["interval_seconds"])
    return {
        "id": row["id"],
        "url": row["url"],
        "interval_seconds": row["interval_seconds"],
        "timeout_seconds": row["timeout_seconds"],
        "status": row["status"],
        "health": health,
        "error": error,
        "last_polled_at": _iso(last_polled_at),
        "next_poll_at": _iso(next_poll_at),
    }


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")
