"""One poll at a time per URL, shared by the scheduler and Poll now."""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone

from backend.db import insert_history
from backend.entries import EntryError
from backend.maintenance import reconcile_entry
from backend.polling import format_console, run_cycle

ALREADY_POLLING = "Can't request this right now. A request is already waiting for a response."


class PollControl:
    """Claims a URL before the request starts and releases it after the result is saved."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._inflight: set[int] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._connection = None

    def attach(self, loop: asyncio.AbstractEventLoop, connection) -> None:
        self._loop = loop
        self._connection = connection

    def running_ids(self) -> set[int]:
        with self._lock:
            return set(self._inflight)

    def claim(self, entry_id: int) -> bool:
        with self._lock:
            if entry_id in self._inflight:
                return False
            self._inflight.add(entry_id)
            return True

    def release(self, entry_id: int) -> None:
        with self._lock:
            self._inflight.discard(entry_id)

    def request_now(self, entry: dict):
        """Start one poll and return its completion.

        None means this URL is already waiting for a response.
        """
        entry_id = entry["id"]
        if not self.claim(entry_id):
            return None
        loop = self._loop
        connection = self._connection
        if loop is None or connection is None:
            self.release(entry_id)
            raise EntryError("Polling is not running.")
        try:
            return asyncio.run_coroutine_threadsafe(run_poll(connection, entry, self), loop)
        except RuntimeError:
            self.release(entry_id)
            raise EntryError("Polling is not running.") from None


async def run_poll(connection, entry: dict, control: PollControl) -> None:
    entry_id = entry["id"]
    url = entry["url"]
    try:
        started_at, duration_ms, outcome = await asyncio.to_thread(
            run_cycle,
            url,
            entry["timeout_seconds"],
            entry["expected_code"],
        )
        insert_history(
            connection,
            entry_id,
            started_at,
            outcome.http_status,
            duration_ms,
            outcome.message,
        )
    except Exception as exc:
        print(f"Failed to save the result for {url}: {exc}")
        return
    finally:
        control.release(entry_id)
    try:
        reconcile_entry(connection, entry_id, datetime.now(timezone.utc))
    except Exception as exc:
        print(f"Failed to update mail for {url}: {exc}")
    print(format_console(url, outcome.http_status, outcome.message))
