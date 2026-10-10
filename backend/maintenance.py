"""Maintenance windows and the fake mail history they control."""

from __future__ import annotations

from datetime import datetime, timezone

import psycopg

from backend.entries import clamp_page
from backend.mail import (
    ended_message,
    letter_plan,
    maintenance_status,
    merge_windows,
    started_message,
)
from backend.stats import load_incident_bounds

EDGES = ("started", "ended")


class MaintenanceError(Exception):
    """The requested maintenance change cannot be applied."""


def require_target_kind(value: object) -> str:
    if value not in {"url", "group"}:
        raise MaintenanceError("Maintenance target must be a URL or a group.")
    return str(value)


def require_target_id(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise MaintenanceError("Maintenance target id must be an integer of at least 1.")
    return value


def require_maintenance_id(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise MaintenanceError("Maintenance id must be an integer of at least 1.")
    return value


def require_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise MaintenanceError(f"{label} must be a UTC timestamp.")
    text = value.strip().replace("Z", "+00:00")
    if not text:
        raise MaintenanceError(f"{label} must be a UTC timestamp.")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise MaintenanceError(f"{label} must be a UTC timestamp.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_maintenances(
    connection: psycopg.Connection,
    url_page: int,
    url_page_size: int,
    group_page: int,
    group_page_size: int,
    now: datetime | None = None,
) -> dict:
    now = _aware(now)
    with connection.transaction():
        url_rows, url_total, url_page = _page(connection, "url", url_page, url_page_size, now)
        group_rows, group_total, group_page = _page(
            connection, "group", group_page, group_page_size, now
        )
        urls = connection.execute(
            """
            SELECT id, url
            FROM poll_entries
            WHERE status <> 'DELETED'
            ORDER BY url, id
            """
        ).fetchall()
        groups = connection.execute(
            "SELECT id, name FROM poll_groups ORDER BY name, id"
        ).fetchall()
    return {
        "url_maintenances": [_row_payload(row, now) for row in url_rows],
        "url_total": url_total,
        "url_page": url_page,
        "url_page_size": url_page_size,
        "group_maintenances": [_row_payload(row, now) for row in group_rows],
        "group_total": group_total,
        "group_page": group_page,
        "group_page_size": group_page_size,
        "urls": [{"id": row["id"], "url": row["url"]} for row in urls],
        "groups": [{"id": row["id"], "name": row["name"]} for row in groups],
    }


def create_maintenance(
    connection: psycopg.Connection,
    target_kind: str,
    target_id: int,
    starts_at: datetime,
    ends_at: datetime,
    url_page: int,
    url_page_size: int,
    group_page: int,
    group_page_size: int,
    now: datetime | None = None,
) -> dict:
    now = _aware(now)
    _require_range(starts_at, ends_at)
    with connection.transaction():
        _require_target(connection, target_kind, target_id)
        row = connection.execute(
            """
            INSERT INTO maintenances (
                target_kind, poll_entry_id, poll_group_id, starts_at, ends_at
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, target_kind, poll_entry_id, poll_group_id
            """,
            (target_kind, *_target_columns(target_kind, target_id), starts_at, ends_at),
        ).fetchone()
        _reconcile_targets(connection, row, now)
        _settle_row(connection, row["id"], now)
    return load_maintenances(connection, url_page, url_page_size, group_page, group_page_size, now)


def update_maintenance(
    connection: psycopg.Connection,
    maintenance_id: int,
    target_kind: str,
    target_id: int,
    starts_at: datetime,
    ends_at: datetime,
    url_page: int,
    url_page_size: int,
    group_page: int,
    group_page_size: int,
    now: datetime | None = None,
) -> dict | None:
    now = _aware(now)
    _require_range(starts_at, ends_at)
    with connection.transaction():
        previous = _lock(connection, maintenance_id)
        if previous is None:
            return None
        _require_target(connection, target_kind, target_id)
        connection.execute(
            """
            UPDATE maintenances
            SET target_kind = %s,
                poll_entry_id = %s,
                poll_group_id = %s,
                starts_at = %s,
                ends_at = %s,
                settled_at = NULL
            WHERE id = %s
            """,
            (
                target_kind,
                *_target_columns(target_kind, target_id),
                starts_at,
                ends_at,
                maintenance_id,
            ),
        )
        current = _lock(connection, maintenance_id)
        _reconcile_targets(connection, previous, now)
        if current is not None:
            _reconcile_targets(connection, current, now)
            _settle_row(connection, maintenance_id, now)
    return load_maintenances(connection, url_page, url_page_size, group_page, group_page_size, now)


def delete_maintenance(
    connection: psycopg.Connection,
    maintenance_id: int,
    url_page: int,
    url_page_size: int,
    group_page: int,
    group_page_size: int,
    now: datetime | None = None,
) -> dict | None:
    """Close an open window at now, freeze mail, then remove the row.

    A window that already ended keeps the letters it already produced.
    """
    now = _aware(now)
    with connection.transaction():
        row = _lock(connection, maintenance_id)
        if row is None:
            return None
        if row["starts_at"] < now < row["ends_at"]:
            connection.execute(
                """
                UPDATE maintenances
                SET ends_at = %s, settled_at = NULL
                WHERE id = %s
                """,
                (now, maintenance_id),
            )
        _reconcile_targets(connection, row, now)
        connection.execute("DELETE FROM maintenances WHERE id = %s", (maintenance_id,))
    return load_maintenances(connection, url_page, url_page_size, group_page, group_page_size, now)


def list_mails(connection: psycopg.Connection) -> dict:
    rows = connection.execute(
        """
        SELECT id, addresses, message
        FROM sent_mails
        ORDER BY id DESC
        """
    ).fetchall()
    return {
        "mails": [
            {
                "id": row["id"],
                "addresses": list(row["addresses"] or []),
                "message": row["message"],
            }
            for row in rows
        ]
    }


def reconcile_all(connection: psycopg.Connection, now: datetime | None = None) -> None:
    """Catch letters whose maintenance ended while this process was stopped."""
    now = _aware(now)
    rows = connection.execute(
        "SELECT id FROM poll_entries WHERE status <> 'DELETED'"
    ).fetchall()
    for row in rows:
        reconcile_entry(connection, row["id"], now)
    connection.execute(
        """
        UPDATE maintenances
        SET settled_at = %s
        WHERE ends_at <= %s AND settled_at IS NULL
        """,
        (now, now),
    )


def settle_ended_maintenances(connection: psycopg.Connection, now: datetime | None = None) -> None:
    """Send deferred letters once the last covering window has ended."""
    now = _aware(now)
    rows = connection.execute(
        """
        SELECT id, target_kind, poll_entry_id, poll_group_id
        FROM maintenances
        WHERE ends_at <= %s AND settled_at IS NULL
        """,
        (now,),
    ).fetchall()
    seen: set[int] = set()
    for row in rows:
        for entry_id in _affected_entry_ids(connection, row):
            if entry_id in seen:
                continue
            seen.add(entry_id)
            reconcile_entry(connection, entry_id, now)
    if not rows:
        return
    connection.execute(
        "UPDATE maintenances SET settled_at = %s WHERE id = ANY(%s)",
        (now, [row["id"] for row in rows]),
    )


def reconcile_url(connection: psycopg.Connection, url: str, now: datetime | None = None) -> None:
    now = _aware(now)
    row = connection.execute(
        """
        SELECT id
        FROM poll_entries
        WHERE url = %s AND status <> 'DELETED'
        """,
        (url,),
    ).fetchone()
    if row is None:
        return
    reconcile_entry(connection, row["id"], now)


def reconcile_entry(connection: psycopg.Connection, entry_id: int, now: datetime | None = None) -> None:
    """Write at most one started row and one ended row for each incident."""
    now = _aware(now)
    entry = connection.execute(
        """
        SELECT id, url, interval_seconds, status, group_id
        FROM poll_entries
        WHERE id = %s
        """,
        (entry_id,),
    ).fetchone()
    if entry is None or entry["status"] == "DELETED":
        return
    if not isinstance(entry["interval_seconds"], int) or entry["interval_seconds"] < 1:
        return
    incidents = load_incident_bounds(connection, entry_id, entry["interval_seconds"], now)
    windows = _windows_for(connection, entry_id, entry["group_id"])
    addresses = _addresses(connection, entry_id)
    latest = connection.execute(
        """
        SELECT polled_at
        FROM poll_history
        WHERE poll_entry_id = %s
        ORDER BY polled_at DESC, id DESC
        LIMIT 1
        """,
        (entry_id,),
    ).fetchone()
    latest_poll = None if latest is None else latest["polled_at"]
    for incident in incidents:
        plan = letter_plan(incident["start"], incident["end"], windows, now)
        stored = _mail_state(connection, entry_id, incident["start"])
        for edge in EDGES:
            if stored[edge] != "wait":
                continue
            action = plan[edge]
            if action == "wait":
                continue
            if action == "skip" or _is_historical(edge, incident, windows, latest_poll):
                _set_edge(connection, entry_id, incident["start"], edge, "skip")
                stored[edge] = "skip"
                continue
            if not addresses or (edge == "ended" and incident["end"] is None):
                continue
            message = (
                started_message(entry["url"], incident["start"])
                if edge == "started"
                else ended_message(entry["url"], incident["start"], incident["end"])
            )
            inserted = connection.execute(
                """
                INSERT INTO sent_mails (
                    poll_entry_id, incident_start, kind, addresses, message, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (poll_entry_id, incident_start, kind) DO NOTHING
                """,
                (entry_id, incident["start"], edge, addresses, message, now),
            )
            _set_edge(connection, entry_id, incident["start"], edge, "sent")
            stored[edge] = "sent"
            if inserted.rowcount == 1:
                print(f"Recorded mail for {entry['url']}: {message}")


def _page(
    connection: psycopg.Connection,
    target_kind: str,
    page: int,
    page_size: int,
    now: datetime,
) -> tuple[list[dict], int, int]:
    total = connection.execute(
        "SELECT COUNT(*) AS total FROM maintenances WHERE target_kind = %s",
        (target_kind,),
    ).fetchone()["total"]
    page = clamp_page(page, page_size, total)
    offset = (page - 1) * page_size
    rows = connection.execute(
        """
        SELECT
            maintenances.id,
            maintenances.target_kind,
            maintenances.poll_entry_id,
            maintenances.poll_group_id,
            maintenances.starts_at,
            maintenances.ends_at,
            EXISTS (
                SELECT 1
                FROM poll_history
                JOIN poll_entries ON poll_entries.id = poll_history.poll_entry_id
                WHERE poll_entries.status <> 'DELETED'
                  AND poll_history.message <> 'OK'
                  AND poll_history.polled_at >= maintenances.starts_at
                  AND poll_history.polled_at < LEAST(maintenances.ends_at, %s)
                  AND (
                    (
                        maintenances.target_kind = 'url'
                        AND poll_entries.id = maintenances.poll_entry_id
                    )
                    OR (
                        maintenances.target_kind = 'group'
                        AND poll_entries.group_id = maintenances.poll_group_id
                    )
                  )
            ) AS saw_down
        FROM maintenances
        WHERE maintenances.target_kind = %s
        ORDER BY maintenances.starts_at DESC, maintenances.id DESC
        LIMIT %s OFFSET %s
        """,
        (now, target_kind, page_size, offset),
    ).fetchall()
    return list(rows), total, page


def _row_payload(row: dict, now: datetime) -> dict:
    target_id = row["poll_entry_id"] if row["target_kind"] == "url" else row["poll_group_id"]
    return {
        "id": row["id"],
        "target_kind": row["target_kind"],
        "target_id": target_id,
        "starts_at": _iso(row["starts_at"]),
        "ends_at": _iso(row["ends_at"]),
        "status": maintenance_status(row["starts_at"], row["ends_at"], bool(row["saw_down"]), now),
    }


def _is_historical(edge: str, incident: dict, windows: list[tuple], latest_poll: datetime | None) -> bool:
    """Closed incidents from before this recorder existed are not mailed again.

    A letter that waited for a maintenance window is not historical: its edge
    sits inside that window. An open incident still needs its started letter.
    """
    moment = incident["start"] if edge == "started" else incident["end"]
    if moment is not None and _inside_window(moment, windows):
        return False
    if edge == "started":
        return incident["end"] is not None
    return latest_poll is None or incident["end"] != latest_poll


def _inside_window(moment: datetime, windows: list[tuple]) -> bool:
    for start, end in merge_windows(windows):
        if start <= moment < end:
            return True
    return False


def _windows_for(connection: psycopg.Connection, entry_id: int, group_id: int | None) -> list[tuple]:
    rows = connection.execute(
        """
        SELECT starts_at, ends_at
        FROM maintenances
        WHERE poll_entry_id = %s
           OR poll_group_id = %s
        """,
        (entry_id, group_id),
    ).fetchall()
    return [(row["starts_at"], row["ends_at"]) for row in rows]


def _addresses(connection: psycopg.Connection, entry_id: int) -> list[str]:
    rows = connection.execute(
        """
        SELECT poll_group_emails.address
        FROM poll_entries
        JOIN poll_group_emails ON poll_group_emails.poll_group_id = poll_entries.group_id
        WHERE poll_entries.id = %s
          AND poll_entries.status <> 'DELETED'
        ORDER BY poll_group_emails.address
        """,
        (entry_id,),
    ).fetchall()
    return [row["address"] for row in rows]


def _mail_state(connection: psycopg.Connection, entry_id: int, incident_start: datetime) -> dict[str, str]:
    row = connection.execute(
        """
        SELECT started, ended
        FROM incident_mail
        WHERE poll_entry_id = %s AND incident_start = %s
        """,
        (entry_id, incident_start),
    ).fetchone()
    if row is None:
        return {"started": "wait", "ended": "wait"}
    return {"started": row["started"], "ended": row["ended"]}


def _set_edge(
    connection: psycopg.Connection,
    entry_id: int,
    incident_start: datetime,
    edge: str,
    state: str,
) -> None:
    if edge == "started":
        connection.execute(
            """
            INSERT INTO incident_mail (poll_entry_id, incident_start, started, ended)
            VALUES (%s, %s, %s, 'wait')
            ON CONFLICT (poll_entry_id, incident_start)
            DO UPDATE SET started = EXCLUDED.started
            WHERE incident_mail.started = 'wait'
            """,
            (entry_id, incident_start, state),
        )
        return
    connection.execute(
        """
        INSERT INTO incident_mail (poll_entry_id, incident_start, started, ended)
        VALUES (%s, %s, 'wait', %s)
        ON CONFLICT (poll_entry_id, incident_start)
        DO UPDATE SET ended = EXCLUDED.ended
        WHERE incident_mail.ended = 'wait'
        """,
        (entry_id, incident_start, state),
    )


def _reconcile_targets(connection: psycopg.Connection, row: dict, now: datetime) -> None:
    for entry_id in _affected_entry_ids(connection, row):
        reconcile_entry(connection, entry_id, now)


def _affected_entry_ids(connection: psycopg.Connection, row: dict) -> list[int]:
    if row["target_kind"] == "url" and row["poll_entry_id"] is not None:
        return [row["poll_entry_id"]]
    if row["poll_group_id"] is None:
        return []
    members = connection.execute(
        """
        SELECT id
        FROM poll_entries
        WHERE group_id = %s AND status <> 'DELETED'
        """,
        (row["poll_group_id"],),
    ).fetchall()
    return [item["id"] for item in members]


def _settle_row(connection: psycopg.Connection, maintenance_id: int, now: datetime) -> None:
    connection.execute(
        """
        UPDATE maintenances
        SET settled_at = %s
        WHERE id = %s AND ends_at <= %s AND settled_at IS NULL
        """,
        (now, maintenance_id, now),
    )


def _lock(connection: psycopg.Connection, maintenance_id: int) -> dict | None:
    return connection.execute(
        """
        SELECT id, target_kind, poll_entry_id, poll_group_id, starts_at, ends_at
        FROM maintenances
        WHERE id = %s
        FOR UPDATE
        """,
        (maintenance_id,),
    ).fetchone()


def _require_target(connection: psycopg.Connection, target_kind: str, target_id: int) -> None:
    if target_kind == "url":
        row = connection.execute(
            """
            SELECT id
            FROM poll_entries
            WHERE id = %s AND status <> 'DELETED'
            """,
            (target_id,),
        ).fetchone()
        if row is None:
            raise MaintenanceError("URL not found.")
        return
    row = connection.execute(
        "SELECT id FROM poll_groups WHERE id = %s",
        (target_id,),
    ).fetchone()
    if row is None:
        raise MaintenanceError("Group not found.")


def _require_range(starts_at: datetime, ends_at: datetime) -> None:
    if ends_at <= starts_at:
        raise MaintenanceError("Maintenance end must be after the start.")


def _target_columns(target_kind: str, target_id: int) -> tuple[int | None, int | None]:
    if target_kind == "url":
        return target_id, None
    return None, target_id


def _aware(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
