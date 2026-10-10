"""Poll ACTIVE entries until the process is stopped."""

from __future__ import annotations

import asyncio
import sys
import threading
from datetime import datetime, timedelta, timezone

from backend.config import load_http_config
from backend.db import DatabaseError, connect, ensure_schema, load_active_entries
from backend.entries import EntryError
from backend.poll_control import PollControl
from backend.polling import is_due
from backend.server import ApiServer

TICK_SECONDS = 1.0


def main() -> None:
    try:
        connection = connect()
    except DatabaseError as exc:
        print(f"No access to the database: {exc}")
        print("Exiting.")
        sys.exit(1)
    try:
        ensure_schema(connection)
    except DatabaseError as exc:
        print(exc)
        print("Exiting.")
        connection.close()
        sys.exit(1)
    try:
        port, jwt_secret = _http_settings()
    except ValueError as exc:
        print(exc)
        print("Exiting.")
        connection.close()
        sys.exit(1)
    try:
        control = PollControl()
        server = ApiServer(port, jwt_secret, control)
    except OSError as exc:
        print(f"Cannot listen on port {port}: {exc}")
        print("Exiting.")
        connection.close()
        sys.exit(1)
    print(f"HTTP API listening on port {port}.")
    print("Polling started.")
    thread = threading.Thread(target=server.serve_forever, name="http", daemon=True)
    thread.start()
    try:
        asyncio.run(supervise(connection, control))
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        server.shutdown()
        server.server_close()
        connection.close()


async def supervise(connection, control: PollControl) -> None:
    control.attach(asyncio.get_running_loop(), connection)
    invalid: set[int] = set()
    while True:
        try:
            entries = load_active_entries(connection)
        except Exception as exc:
            print(f"Failed to read poll entries: {exc}")
            await asyncio.sleep(TICK_SECONDS)
            continue
        now = datetime.now(timezone.utc)
        running = control.running_ids()
        for entry in entries:
            entry_id = entry["id"]
            if entry_id in running:
                continue
            if not _usable(entry, invalid):
                continue
            last_polled_at = entry["last_polled_at"]
            if last_polled_at is not None and last_polled_at.tzinfo is None:
                last_polled_at = last_polled_at.replace(tzinfo=timezone.utc)
            if not is_due(last_polled_at, entry["interval_seconds"], now):
                continue
            try:
                control.request_now(dict(entry))
            except EntryError as exc:
                print(f"Failed to start the poll for {entry['url']}: {exc}")
        await asyncio.sleep(_sleep_seconds(entries, control.running_ids(), now))


def _usable(entry: dict, invalid: set[int]) -> bool:
    entry_id = entry["id"]
    timeout = entry["timeout_seconds"]
    interval = entry["interval_seconds"]
    if isinstance(timeout, int) and timeout >= 1 and isinstance(interval, int) and interval >= 1:
        return True
    if entry_id not in invalid:
        invalid.add(entry_id)
        print(
            f"Skipping {entry['url']}: timeout and polling rate must be integers of at least 1 second."
        )
    return False


def _http_settings() -> tuple[int, str]:
    raw = load_http_config()
    try:
        port = int(raw["port"])
    except ValueError as exc:
        raise ValueError(f"HTTP port in config.ini is not a number: {raw['port']}") from exc
    if port < 1 or port > 65535:
        raise ValueError(f"HTTP port in config.ini is out of range: {raw['port']}")
    secret = raw["jwt_secret"].strip() or "dev-secret"
    return port, secret


def _sleep_seconds(entries: list[dict], inflight: set[int], now: datetime) -> float:
    """Wake for the next due poll, and at least once a second for new rows."""
    wait = TICK_SECONDS
    for entry in entries:
        if entry["id"] in inflight or entry["last_polled_at"] is None:
            continue
        interval = entry["interval_seconds"]
        if not isinstance(interval, int) or interval < 1:
            continue
        due_at = entry["last_polled_at"]
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=timezone.utc)
        remaining = (due_at + timedelta(seconds=interval) - now).total_seconds()
        if remaining > 0:
            wait = min(wait, remaining)
    return max(0.05, wait)


if __name__ == "__main__":
    main()
