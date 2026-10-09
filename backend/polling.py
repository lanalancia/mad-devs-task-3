"""One poll cycle for a single URL.

A cycle sends one request. A timeout is not stored: the same request is sent
once more. Any other result, including the second timeout, becomes one history
row. The next cycle is due interval_seconds after this cycle started.
"""

from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

USER_AGENT = "mad-devs-task-3"


@dataclass(frozen=True)
class Attempt:
    kind: str
    http_status: int | None = None
    error: str | None = None


@dataclass(frozen=True)
class HistoryRow:
    http_status: int | None
    message: str


def finalize(attempt: Attempt, expected_code: int, *, is_retry: bool) -> HistoryRow | None:
    """Return the history row for this attempt.

    None means the first attempt timed out and the caller must retry once.
    """
    if attempt.kind == "timeout":
        if is_retry:
            return HistoryRow(http_status=None, message="Down detected")
        return None
    if attempt.kind == "http":
        status = attempt.http_status
        if status == expected_code:
            return HistoryRow(http_status=status, message="OK")
        return HistoryRow(http_status=status, message=str(status))
    return HistoryRow(http_status=None, message=attempt.error or "request failed")


def is_due(last_polled_at: datetime | None, interval_seconds: int, now: datetime) -> bool:
    if last_polled_at is None:
        return True
    return now >= last_polled_at + timedelta(seconds=interval_seconds)


def format_console(url: str, http_status: int | None, message: str) -> str:
    shown = "-" if http_status is None else str(http_status)
    return f"Requesting {url}, response status: {shown}, message: {message}"


def error_text(exc: BaseException) -> str:
    reason = getattr(exc, "reason", None)
    text = str(reason if reason is not None else exc)
    return " ".join(text.split())[:500] or "request failed"


def is_timeout(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return True
    reason = getattr(exc, "reason", None)
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return True
    return "timed out" in str(exc).lower()


def request_once(url: str, timeout_seconds: int) -> Attempt:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return Attempt(kind="http", http_status=response.status)
    except urllib.error.HTTPError as exc:
        return Attempt(kind="http", http_status=exc.code)
    except Exception as exc:
        if is_timeout(exc):
            return Attempt(kind="timeout")
        return Attempt(kind="error", error=error_text(exc))


def run_cycle(url: str, timeout_seconds: int, expected_code: int) -> tuple[datetime, int, HistoryRow]:
    """Run one cycle. The timestamp is the start of the first request."""
    started_at = datetime.now(timezone.utc)
    started = time.monotonic()
    attempt = request_once(url, timeout_seconds)
    outcome = finalize(attempt, expected_code, is_retry=False)
    if outcome is None:
        attempt = request_once(url, timeout_seconds)
        outcome = finalize(attempt, expected_code, is_retry=True)
    if outcome is None:
        outcome = HistoryRow(http_status=None, message="Down detected")
    duration_ms = max(0, int((time.monotonic() - started) * 1000))
    return started_at, duration_ms, outcome
