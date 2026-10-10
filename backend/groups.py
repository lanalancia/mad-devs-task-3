"""Poll groups: one pause switch for many URLs, plus stored email addresses."""

from __future__ import annotations

import psycopg

NAME_LIMIT = 50
EMAIL_LIMIT = 200


class GroupError(Exception):
    """The requested group change cannot be applied."""


def response_status(group_paused: bool, members: list[tuple[str, str | None]]) -> str:
    """Priority: empty, every URL paused, the group pause, otherwise polling."""
    if not members:
        return "EMPTY"
    if all(status == "PAUSED" for status, _message in members):
        return "URLS_PAUSED"
    if group_paused:
        return "GROUP_PAUSED"
    if all(status in {"ACTIVE", "PAUSED"} for status, _message in members):
        return "POLLING"
    return "ERROR"


def group_health(status: str, members: list[tuple[str, str | None]]) -> str:
    """UP or DOWN only while the group is polling. Paused URLs are left out."""
    if status != "POLLING":
        return "NO_DATA_YET"
    active = [message for member_status, message in members if member_status != "PAUSED"]
    if any(message is not None and message != "OK" for message in active):
        return "DOWN"
    if active and all(message == "OK" for message in active):
        return "UP"
    return "NO_DATA_YET"


def poll_state(status: str, group_paused: bool | None) -> str:
    """The URL's own pause wins. A group pause applies only while the URL is active."""
    if status != "ACTIVE":
        return "URL_PAUSED"
    if group_paused:
        return "GROUP_PAUSED"
    return "ACTIVE"


def should_poll(status: str, group_paused: bool | None) -> bool:
    """Poll when the URL is active and its group, if it has one, is not paused."""
    return status == "ACTIVE" and not group_paused


def require_group_name(value: object) -> str:
    if not isinstance(value, str):
        raise GroupError("Name must be a string.")
    name = value.strip()
    if not name:
        raise GroupError("Name is required.")
    if len(name) > NAME_LIMIT:
        raise GroupError("Name must be at most 50 characters.")
    return name


def require_group_id(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise GroupError("Group id must be an integer of at least 1.")
    return value


def require_email(value: object) -> str:
    if not isinstance(value, str):
        raise GroupError("Email must be a string.")
    address = value.strip()
    if not address:
        raise GroupError("Email is required.")
    if len(address) > EMAIL_LIMIT or any(character.isspace() for character in address):
        raise GroupError("Email must be an email address.")
    local, separator, domain = address.partition("@")
    if not separator or not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise GroupError("Email must be an email address.")
    return address


def require_email_id(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise GroupError("Email id must be an integer of at least 1.")
    return value


def require_paused(value: object) -> bool:
    if not isinstance(value, bool):
        raise GroupError("Paused must be true or false.")
    return value


def load_groups(connection: psycopg.Connection) -> dict:
    with connection.transaction():
        groups = connection.execute(
            "SELECT id, name, paused FROM poll_groups ORDER BY id"
        ).fetchall()
        members = connection.execute(
            """
            SELECT
                poll_entries.group_id,
                poll_entries.status,
                latest.message AS last_message
            FROM poll_entries
            LEFT JOIN LATERAL (
                SELECT message
                FROM poll_history
                WHERE poll_history.poll_entry_id = poll_entries.id
                ORDER BY polled_at DESC, poll_history.id DESC
                LIMIT 1
            ) AS latest ON TRUE
            WHERE poll_entries.group_id IS NOT NULL
              AND poll_entries.status <> 'DELETED'
            """
        ).fetchall()
        emails = connection.execute(
            """
            SELECT id, poll_group_id, address
            FROM poll_group_emails
            ORDER BY id
            """
        ).fetchall()
    by_group: dict[int, list[tuple[str, str | None]]] = {}
    for row in members:
        by_group.setdefault(row["group_id"], []).append((row["status"], row["last_message"]))
    mail_by_group: dict[int, list[dict]] = {}
    for row in emails:
        mail_by_group.setdefault(row["poll_group_id"], []).append(
            {"id": row["id"], "address": row["address"]}
        )
    return {
        "groups": [
            _serialize(row, by_group.get(row["id"], []), mail_by_group.get(row["id"], []))
            for row in groups
        ]
    }


def create_group(connection: psycopg.Connection, name: str) -> dict:
    try:
        with connection.transaction():
            _reject_duplicate_name(connection, name, None)
            connection.execute(
                "INSERT INTO poll_groups (name, paused) VALUES (%s, false)",
                (name,),
            )
    except psycopg.errors.UniqueViolation as exc:
        raise GroupError("A group with this name already exists.") from exc
    return load_groups(connection)


def update_group(
    connection: psycopg.Connection,
    group_id: int,
    name: str | None,
    paused: bool | None,
) -> dict | None:
    if name is None and paused is None:
        raise GroupError("Nothing to update.")
    try:
        with connection.transaction():
            current = connection.execute(
                "SELECT id FROM poll_groups WHERE id = %s",
                (group_id,),
            ).fetchone()
            if current is None:
                return None
            if name is not None:
                _reject_duplicate_name(connection, name, group_id)
                updated = connection.execute(
                    "UPDATE poll_groups SET name = %s WHERE id = %s",
                    (name, group_id),
                )
                if updated.rowcount != 1:
                    return None
            if paused is not None:
                updated = connection.execute(
                    "UPDATE poll_groups SET paused = %s WHERE id = %s",
                    (paused, group_id),
                )
                if updated.rowcount != 1:
                    return None
    except psycopg.errors.UniqueViolation as exc:
        raise GroupError("A group with this name already exists.") from exc
    return load_groups(connection)


def delete_group(connection: psycopg.Connection, group_id: int) -> dict | None:
    with connection.transaction():
        current = connection.execute(
            "SELECT id FROM poll_groups WHERE id = %s",
            (group_id,),
        ).fetchone()
        if current is None:
            return None
        connection.execute(
            "UPDATE poll_entries SET group_id = NULL WHERE group_id = %s",
            (group_id,),
        )
        connection.execute("DELETE FROM poll_groups WHERE id = %s", (group_id,))
    return load_groups(connection)


def save_email(connection: psycopg.Connection, group_id: int, address: str) -> dict | None:
    try:
        with connection.transaction():
            group = connection.execute(
                "SELECT id FROM poll_groups WHERE id = %s",
                (group_id,),
            ).fetchone()
            if group is None:
                return None
            _reject_duplicate_email(connection, group_id, address, None)
            connection.execute(
                """
                INSERT INTO poll_group_emails (poll_group_id, address)
                VALUES (%s, %s)
                """,
                (group_id, address),
            )
    except psycopg.errors.UniqueViolation as exc:
        raise GroupError("This email is already in the group.") from exc
    return load_groups(connection)


def update_email(connection: psycopg.Connection, email_id: int, address: str) -> dict | None:
    try:
        with connection.transaction():
            current = connection.execute(
                "SELECT id, poll_group_id FROM poll_group_emails WHERE id = %s",
                (email_id,),
            ).fetchone()
            if current is None:
                return None
            _reject_duplicate_email(connection, current["poll_group_id"], address, email_id)
            updated = connection.execute(
                "UPDATE poll_group_emails SET address = %s WHERE id = %s",
                (address, email_id),
            )
            if updated.rowcount != 1:
                return None
    except psycopg.errors.UniqueViolation as exc:
        raise GroupError("This email is already in the group.") from exc
    return load_groups(connection)


def delete_email(connection: psycopg.Connection, email_id: int) -> dict | None:
    with connection.transaction():
        updated = connection.execute(
            "DELETE FROM poll_group_emails WHERE id = %s",
            (email_id,),
        )
        if updated.rowcount != 1:
            return None
    return load_groups(connection)


def _serialize(row: dict, members: list[tuple[str, str | None]], emails: list[dict]) -> dict:
    status = response_status(row["paused"], members)
    return {
        "id": row["id"],
        "name": row["name"],
        "paused": row["paused"],
        "url_count": len(members),
        "response_status": status,
        "health": group_health(status, members),
        "emails": emails,
    }


def _reject_duplicate_name(connection: psycopg.Connection, name: str, group_id: int | None) -> None:
    row = connection.execute(
        """
        SELECT id
        FROM poll_groups
        WHERE name = %s AND (%s::bigint IS NULL OR id <> %s)
        """,
        (name, group_id, group_id),
    ).fetchone()
    if row is not None:
        raise GroupError("A group with this name already exists.")


def _reject_duplicate_email(
    connection: psycopg.Connection,
    group_id: int,
    address: str,
    email_id: int | None,
) -> None:
    row = connection.execute(
        """
        SELECT id
        FROM poll_group_emails
        WHERE poll_group_id = %s
          AND lower(address) = lower(%s)
          AND (%s::bigint IS NULL OR id <> %s)
        """,
        (group_id, address, email_id, email_id),
    ).fetchone()
    if row is not None:
        raise GroupError("This email is already in the group.")
