"""Visible poll entries: one page at a time, soft-deleted rows excluded."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import psycopg

from backend.auth import passwords_match
from backend.groups import poll_state
from backend.urls import UrlError, normalize_url

PAGE_SIZES = (10, 25, 50, 100)
DEFAULT_EXPECTED_CODE = 200
MIN_INTERVAL_SECONDS = 30
MAX_INTERVAL_SECONDS = 3600
MIN_EXPECTED_CODE = 100
MAX_EXPECTED_CODE = 599


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


def require_interval(value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < MIN_INTERVAL_SECONDS
        or value > MAX_INTERVAL_SECONDS
    ):
        raise EntryError("Polling rate must be an integer from 30 to 3600.")
    return value


def require_expected_code(value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < MIN_EXPECTED_CODE
        or value > MAX_EXPECTED_CODE
    ):
        raise EntryError("Expected code must be an integer from 100 to 599.")
    return value


def require_url(value: object) -> str:
    if not isinstance(value, str):
        raise EntryError("URL must be a string.")
    try:
        return normalize_url(value)
    except UrlError as exc:
        raise EntryError(str(exc)) from exc


def require_saved_url(value: object) -> str:
    """The address already stored on a row. Deleting it does not re-check the format."""
    if not isinstance(value, str):
        raise EntryError("URL must be a string.")
    url = value.strip()
    if not url:
        raise EntryError("URL is required.")
    return url


def require_entry_id(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise EntryError("Entry id must be an integer of at least 1.")
    return value


def status_event(previous: str, new: str) -> str | None:
    """Pause and resume are logged. Editing numbers on the same status is not."""
    if previous == "ACTIVE" and new == "PAUSED":
        return "paused"
    if previous == "PAUSED" and new == "ACTIVE":
        return "resumed"
    return None


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
                poll_entries.expected_code,
                poll_entries.status,
                poll_entries.group_id,
                poll_groups.paused AS group_paused,
                latest.polled_at AS last_polled_at,
                latest.message AS last_message
            FROM poll_entries
            LEFT JOIN poll_groups ON poll_groups.id = poll_entries.group_id
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
    expected_code: int = DEFAULT_EXPECTED_CODE,
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
                    (url, timeout_seconds, interval_seconds, expected_code),
                )
            else:
                updated = connection.execute(
                    """
                    UPDATE poll_entries
                    SET timeout_seconds = %s,
                        interval_seconds = %s,
                        expected_code = %s,
                        status = 'PAUSED'
                    WHERE url = %s AND status = 'DELETED'
                    RETURNING id
                    """,
                    (timeout_seconds, interval_seconds, expected_code, url),
                )
                restored = updated.fetchone()
                if restored is None:
                    return "exists", None
                _record_event(connection, restored["id"], "restored")
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
    submitted: str | None = None,
    expected_code: int = DEFAULT_EXPECTED_CODE,
) -> dict | None:
    with connection.transaction():
        current = connection.execute(
            """
            SELECT id, status
            FROM poll_entries
            WHERE url = %s AND status <> 'DELETED'
            """,
            (_stored_url(connection, url, submitted),),
        ).fetchone()
        if current is None:
            return None
        updated = connection.execute(
            """
            UPDATE poll_entries
            SET interval_seconds = %s,
                timeout_seconds = %s,
                expected_code = %s,
                status = %s
            WHERE id = %s AND status <> 'DELETED'
            """,
            (interval_seconds, timeout_seconds, expected_code, status, current["id"]),
        )
        if updated.rowcount != 1:
            return None
        kind = status_event(current["status"], status)
        if kind is not None:
            _record_event(connection, current["id"], kind)
    return load_page(connection, page, page_size)


def delete_entry(
    connection: psycopg.Connection,
    url: str,
    page: int,
    page_size: int,
) -> dict | None:
    with connection.transaction():
        current = connection.execute(
            """
            SELECT id
            FROM poll_entries
            WHERE url = %s AND status <> 'DELETED'
            """,
            (url,),
        ).fetchone()
        if current is None:
            return None
        updated = connection.execute(
            """
            UPDATE poll_entries
            SET status = 'DELETED'
            WHERE id = %s AND status <> 'DELETED'
            """,
            (current["id"],),
        )
        if updated.rowcount != 1:
            return None
        _record_event(connection, current["id"], "deleted")
    return load_page(connection, page, page_size)


def assign_group(
    connection: psycopg.Connection,
    url: str,
    group_id: int | None,
    page: int,
    page_size: int,
) -> dict | None:
    """Point a visible URL at a group. None clears it. Deleting the URL keeps the value."""
    with connection.transaction():
        current = connection.execute(
            """
            SELECT id
            FROM poll_entries
            WHERE url = %s AND status <> 'DELETED'
            """,
            (url,),
        ).fetchone()
        if current is None:
            return None
        if group_id is not None:
            group = connection.execute(
                "SELECT id FROM poll_groups WHERE id = %s",
                (group_id,),
            ).fetchone()
            if group is None:
                raise EntryError("Group not found.")
        updated = connection.execute(
            """
            UPDATE poll_entries
            SET group_id = %s
            WHERE id = %s AND status <> 'DELETED'
            """,
            (group_id, current["id"]),
        )
        if updated.rowcount != 1:
            return None
    return load_page(connection, page, page_size)


def _stored_url(connection: psycopg.Connection, normalized: str, submitted: str | None) -> str:
    """Keep a saved address that could not be rewritten to the normalized form."""
    if not isinstance(submitted, str):
        return normalized
    raw = submitted.strip()
    if not raw or raw == normalized:
        return normalized
    found = connection.execute(
        "SELECT id FROM poll_entries WHERE url = %s",
        (raw,),
    ).fetchone()
    if found is None:
        return normalized
    return raw


def load_poll_target(connection: psycopg.Connection, entry_id: int) -> dict | None:
    """One check that can be polled now, including a paused URL or a paused group."""
    row = connection.execute(
        """
        SELECT id, url, timeout_seconds, interval_seconds, expected_code, status
        FROM poll_entries
        WHERE id = %s AND status <> 'DELETED'
        """,
        (entry_id,),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def _record_event(connection: psycopg.Connection, poll_entry_id: int, kind: str) -> None:
    connection.execute(
        """
        INSERT INTO poll_entry_events (poll_entry_id, kind, happened_at)
        VALUES (%s, %s, %s)
        """,
        (poll_entry_id, kind, datetime.now(timezone.utc)),
    )


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
        "expected_code": row["expected_code"],
        "status": row["status"],
        "group_id": row["group_id"],
        "poll_state": poll_state(row["status"], row["group_paused"]),
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
