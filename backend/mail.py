"""When a URL incident should produce a fake email.

Overlapping windows, including a URL window and a group window, are one long
maintenance. A gap splits them. Ending one window and starting the next in the
same UTC minute does not split them.
"""

from __future__ import annotations

from datetime import datetime, timezone

Window = tuple[datetime, datetime]
Edge = str


def maintenance_status(starts_at: datetime, ends_at: datetime, saw_down: bool, now: datetime) -> str:
    """Display status. ENDED wins after the end, including when a poll went down."""
    starts_at = _utc(starts_at)
    ends_at = _utc(ends_at)
    now = _utc(now)
    if now < starts_at:
        return "NOT_STARTED"
    if now >= ends_at:
        return "ENDED"
    if saw_down:
        return "STARTED_AND_DOWN"
    return "STARTED_AND_UP"


def merge_windows(windows: list[Window]) -> list[Window]:
    """Fold overlapping, touching, and same-minute windows into long stretches."""
    ordered = sorted((_utc(start), _utc(end)) for start, end in windows if _utc(end) > _utc(start))
    merged: list[Window] = []
    for start, end in ordered:
        if not merged or not _joins(merged[-1][1], start):
            merged.append((start, end))
            continue
        previous_start, previous_end = merged[-1]
        merged[-1] = (previous_start, max(previous_end, end))
    return merged


def letter_plan(
    incident_start: datetime,
    incident_end: datetime | None,
    windows: list[Window],
    now: datetime,
) -> dict[str, Edge]:
    """wait, send, or skip for the started edge and the ended edge.

    skip is final: both edges fell inside one long maintenance that is already over.
    send for an edge inside a maintenance waits until that long maintenance ends.
    """
    incident_start = _utc(incident_start)
    incident_end = None if incident_end is None else _utc(incident_end)
    now = _utc(now)
    merged = merge_windows(windows)
    return {
        "started": _edge(incident_start, incident_end, merged, now),
        "ended": _edge(incident_end, incident_start, merged, now),
    }


def format_timestamp(moment: datetime) -> str:
    moment = _utc(moment).replace(microsecond=0)
    return moment.strftime("%Y-%m-%d %H:%M:%S UTC")


def started_message(url: str, started_at: datetime) -> str:
    return f"{url} downtime incident started at {format_timestamp(started_at)}."


def ended_message(url: str, started_at: datetime, ended_at: datetime) -> str:
    started = format_timestamp(started_at)
    ended = format_timestamp(ended_at)
    return f"{url} downtime incident ended. It was started at {started} and ended at {ended}."


def _edge(
    moment: datetime | None,
    other: datetime | None,
    windows: list[Window],
    now: datetime,
) -> Edge:
    if moment is None:
        return "wait"
    window = _containing(windows, moment)
    if window is None:
        return "send" if now >= moment else "wait"
    other_inside = other is not None and _contains(window, other)
    if now < window[1]:
        return "wait"
    if other_inside:
        return "skip"
    return "send"


def _containing(windows: list[Window], moment: datetime) -> Window | None:
    for window in windows:
        if _contains(window, moment):
            return window
    return None


def _contains(window: Window, moment: datetime) -> bool:
    return window[0] <= moment < window[1]


def _joins(previous_end: datetime, next_start: datetime) -> bool:
    if next_start <= previous_end:
        return True
    return _minute(previous_end) == _minute(next_start)


def _minute(value: datetime) -> datetime:
    return value.replace(second=0, microsecond=0)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
