"""Uptime, response-time graph, and incident log for one poll entry."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import psycopg

from backend.entries import EntryError, clamp_page

WINDOWS = {"day": 24, "week": 24 * 7, "month": 24 * 30}
GRAPH_DOTS = 500
GAP_EXTRA_SECONDS = 60
REASONS = {
    "paused": "polling was paused",
    "deactivated": "entry was deactivated",
    "down": "Server was down",
}


def require_window(value: object) -> str:
    if value not in WINDOWS:
        raise EntryError("Window must be day, week, or month.")
    return str(value)


def parse_day(value: object) -> date | None:
    """Empty means the caller picks the default. Anything else is YYYY-MM-DD."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise EntryError("Date must be YYYY-MM-DD.")
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise EntryError("Date must be YYYY-MM-DD.") from exc


def load_statistics(
    connection: psycopg.Connection,
    entry_id: int,
    window: str,
    day_from: date | None,
    day_to: date | None,
    page: int,
    page_size: int,
    now: datetime | None = None,
) -> dict | None:
    entry = connection.execute(
        """
        SELECT id, url, interval_seconds
        FROM poll_entries
        WHERE id = %s AND status <> 'DELETED'
        """,
        (entry_id,),
    ).fetchone()
    if entry is None:
        return None
    checks = connection.execute(
        """
        SELECT id, polled_at, http_status, duration_ms, message
        FROM poll_history
        WHERE poll_entry_id = %s
        ORDER BY polled_at, id
        """,
        (entry_id,),
    ).fetchall()
    events = connection.execute(
        """
        SELECT id, kind, happened_at
        FROM poll_entry_events
        WHERE poll_entry_id = %s
        ORDER BY happened_at, id
        """,
        (entry_id,),
    ).fetchall()
    report = build_statistics(
        checks=[dict(row) for row in checks],
        events=[dict(row) for row in events],
        interval_seconds=entry["interval_seconds"],
        window=window,
        day_from=day_from,
        day_to=day_to,
        page=page,
        page_size=page_size,
        now=now or datetime.now(timezone.utc),
    )
    report["id"] = entry["id"]
    report["url"] = entry["url"]
    return report


def build_statistics(
    checks: list[dict],
    events: list[dict],
    interval_seconds: int,
    window: str,
    day_from: date | None,
    day_to: date | None,
    page: int,
    page_size: int,
    now: datetime,
) -> dict:
    now = _aware(now)
    ordered = sorted(
        ({**row, "polled_at": _aware(row["polled_at"])} for row in checks),
        key=lambda row: (row["polled_at"], row.get("id", 0)),
    )
    ordered_events = sorted(
        ({**row, "happened_at": _aware(row["happened_at"])} for row in events),
        key=lambda row: (row["happened_at"], row.get("id", 0)),
    )
    window_start = now - timedelta(hours=WINDOWS[window])
    today = now.date()
    if day_from is None:
        day_from = today - timedelta(days=30)
    if day_to is None:
        day_to = today
    if day_from > day_to:
        raise EntryError("The start date must be on or before the end date.")
    range_start = datetime.combine(day_from, time.min, tzinfo=timezone.utc)
    range_end = datetime.combine(day_to + timedelta(days=1), time.min, tzinfo=timezone.utc)

    in_window = [row for row in ordered if window_start <= row["polled_at"] <= now]
    successful = sum(1 for row in in_window if row["message"] == "OK")
    responded = [row["duration_ms"] for row in in_window if row["http_status"] is not None]
    incidents = _incidents(ordered, interval_seconds, now)
    gaps = _gaps(ordered, ordered_events, interval_seconds)
    rows = [row for row in incidents + gaps if _overlaps(row, range_start, range_end)]
    rows.sort(key=lambda row: row["start"], reverse=True)
    total = len(rows)
    page = clamp_page(page, page_size, total)
    start_index = (page - 1) * page_size
    visible = rows[start_index : start_index + page_size]
    points, max_ms = _graph(in_window, incidents, gaps, window_start, now)
    return {
        "window": window,
        "percentage": None if not in_window else round(100 * successful / len(in_window), 1),
        "average_ms": None if not responded else int(round(sum(responded) / len(responded))),
        "graph": {"max_ms": max_ms, "points": points},
        "from": day_from.isoformat(),
        "to": day_to.isoformat(),
        "page": page,
        "page_size": page_size,
        "total": total,
        "rows": [_serialize_row(row) for row in visible],
    }


def _incidents(checks: list[dict], interval_seconds: int, now: datetime) -> list[dict]:
    found: list[dict] = []
    index = 0
    total = len(checks)
    while index < total:
        if checks[index]["message"] == "OK":
            index += 1
            continue
        end_index = index
        while end_index + 1 < total and checks[end_index + 1]["message"] != "OK":
            if _prolonged(checks[end_index]["polled_at"], checks[end_index + 1]["polled_at"], interval_seconds):
                break
            end_index += 1
        run = checks[index : end_index + 1]
        if len(run) >= 2:
            start = run[0]["polled_at"]
            closed_by_ok = (
                end_index + 1 < total
                and checks[end_index + 1]["message"] == "OK"
                and not _prolonged(checks[end_index]["polled_at"], checks[end_index + 1]["polled_at"], interval_seconds)
            )
            if closed_by_ok:
                end = checks[end_index + 1]["polled_at"]
            elif end_index + 1 < total:
                end = run[-1]["polled_at"]
            else:
                end = None
            groups = _groups(run)
            found.append(
                {
                    "kind": "incident",
                    "start": start,
                    "end": end,
                    "duration_seconds": _duration(start, end, now),
                    "reason": ", ".join(_group_label(group) for group in groups),
                    "groups": groups,
                }
            )
        index = end_index + 1
    return found


def _gaps(checks: list[dict], events: list[dict], interval_seconds: int) -> list[dict]:
    found: list[dict] = []
    for previous, following in zip(checks, checks[1:]):
        found.extend(
            _gap_segments(
                previous["polled_at"],
                following["polled_at"],
                interval_seconds,
                events,
            )
        )
    return found


def _gap_segments(
    previous: datetime,
    following: datetime,
    interval_seconds: int,
    events: list[dict],
) -> list[dict]:
    if not _prolonged(previous, following, interval_seconds):
        return []
    state = "active"
    cursor = previous
    pieces: list[dict | None] = []
    for event in events:
        happened_at = event["happened_at"]
        if happened_at <= previous:
            state = _apply_event(state, event["kind"])
            continue
        if happened_at >= following:
            break
        pieces.append(_piece(cursor, happened_at, state, interval_seconds))
        state = _apply_event(state, event["kind"])
        cursor = happened_at
    pieces.append(_piece(cursor, following, state, interval_seconds))
    return [piece for piece in pieces if piece is not None]


def _piece(start: datetime, end: datetime, state: str, interval_seconds: int) -> dict | None:
    if end <= start:
        return None
    if state == "active":
        if not _prolonged(start, end, interval_seconds):
            return None
        reason_key = "down"
    elif state == "paused":
        reason_key = "paused"
    elif state == "deactivated":
        reason_key = "deactivated"
    else:
        return None
    return {
        "kind": "no_data",
        "start": start,
        "end": end,
        "duration_seconds": _duration(start, end, end),
        "reason": REASONS[reason_key],
        "groups": [],
    }


def _apply_event(state: str, kind: str) -> str:
    if kind == "paused" and state == "active":
        return "paused"
    if kind == "resumed" and state == "paused":
        return "active"
    if kind == "deleted" and state in {"active", "paused"}:
        return "deactivated"
    if kind == "restored" and state == "deactivated":
        return "paused"
    return state


def _graph(
    checks: list[dict],
    incidents: list[dict],
    gaps: list[dict],
    window_start: datetime,
    window_end: datetime,
) -> tuple[list[dict], int]:
    span = (window_end - window_start).total_seconds()
    buckets: list[list[int]] = [[] for _ in range(GRAPH_DOTS)]
    if span > 0:
        for row in checks:
            if row["http_status"] is None:
                continue
            offset = (row["polled_at"] - window_start).total_seconds()
            if offset < 0 or offset > span:
                continue
            slot = min(GRAPH_DOTS - 1, int(offset / span * GRAPH_DOTS))
            buckets[slot].append(row["duration_ms"])
    points: list[dict] = []
    for slot, samples in enumerate(buckets):
        if not samples:
            continue
        at = window_start + timedelta(seconds=span * slot / GRAPH_DOTS)
        previous = points[-1]["at"] if points else None
        connect = previous is not None and not _crosses(previous, at, incidents, gaps)
        points.append(
            {
                "slot": slot,
                "ms": int(round(sum(samples) / len(samples))),
                "connect": connect,
                "at": at,
            }
        )
    peak = max((point["ms"] for point in points), default=0)
    serialized = [
        {"slot": point["slot"], "ms": point["ms"], "connect": point["connect"]}
        for point in points
    ]
    return serialized, max(1000, peak)


def _crosses(previous: datetime, current: datetime, incidents: list[dict], gaps: list[dict]) -> bool:
    for row in incidents + gaps:
        finish = row["end"] if row["end"] is not None else datetime.max.replace(tzinfo=timezone.utc)
        if previous < finish and current >= row["start"]:
            return True
    return False


def _overlaps(row: dict, range_start: datetime, range_end: datetime) -> bool:
    finish = row["end"] if row["end"] is not None else datetime.max.replace(tzinfo=timezone.utc)
    return row["start"] < range_end and finish >= range_start


def _groups(run: list[dict]) -> list[dict]:
    grouped: list[dict] = []
    index_by_key: dict[tuple, int] = {}
    for row in run:
        key = (row["http_status"], row["message"])
        found = index_by_key.get(key)
        if found is None:
            index_by_key[key] = len(grouped)
            grouped.append({"status": row["http_status"], "message": row["message"], "count": 1})
            continue
        grouped[found]["count"] += 1
    return grouped


def _group_label(group: dict) -> str:
    status = group["status"]
    message = group["message"]
    if status is None or str(status) == message:
        label = message
    else:
        label = f"{status} {message}"
    return f"{label} × {group['count']}"


def _prolonged(previous: datetime, following: datetime, interval_seconds: int) -> bool:
    return (following - previous).total_seconds() >= 2 * interval_seconds + GAP_EXTRA_SECONDS


def _duration(start: datetime, end: datetime | None, now: datetime) -> int:
    finish = now if end is None else end
    return max(0, int((finish - start).total_seconds()))


def _serialize_row(row: dict) -> dict:
    return {
        "kind": row["kind"],
        "start": _iso(row["start"]),
        "end": _iso(row["end"]),
        "duration_seconds": row["duration_seconds"],
        "reason": row["reason"],
        "groups": row["groups"],
    }


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")
