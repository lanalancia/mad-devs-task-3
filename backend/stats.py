"""Uptime, response-time graph, and incident log for one poll entry."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import psycopg

from backend.entries import EntryError, clamp_page

WINDOWS = {"day": 24, "week": 24 * 7, "month": 24 * 30}
GRAPH_CHECKS = 100
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


def statistics_fetch_range(
    window: str,
    day_from: date | None,
    day_to: date | None,
    now: datetime,
) -> tuple[datetime, datetime]:
    """Start inclusive and end exclusive for the graph window and the journal."""
    now = _aware(now)
    _resolved_from, _resolved_to, range_start, range_end = _resolved_dates(day_from, day_to, now)
    window_start = now - timedelta(hours=WINDOWS[window])
    return min(window_start, range_start), max(now, range_end)


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
    moment = now or datetime.now(timezone.utc)
    day_from, day_to, range_start, range_end = _resolved_dates(day_from, day_to, moment)
    window_start = moment - timedelta(hours=WINDOWS[window])
    percentage, average_ms = _window_summary(connection, entry_id, window_start, moment)
    points, max_ms, slots = _recent_graph(connection, entry_id, entry["interval_seconds"], moment)
    journal, total, page = _journal(
        connection,
        entry_id,
        entry["interval_seconds"],
        range_start,
        range_end,
        page,
        page_size,
        moment,
    )
    last_polled_at, last_duration_ms = _latest_poll(connection, entry_id)
    return {
        "id": entry["id"],
        "url": entry["url"],
        "window": window,
        "percentage": percentage,
        "average_ms": average_ms,
        "graph": {"max_ms": max_ms, "slots": slots, "points": points},
        "from": day_from.isoformat(),
        "to": day_to.isoformat(),
        "page": page,
        "page_size": page_size,
        "total": total,
        "last_polled_at": last_polled_at,
        "last_duration_ms": last_duration_ms,
        "open_incident_seconds": _open_incident_seconds(connection, entry_id, entry["interval_seconds"], moment),
        "rows": journal,
    }


def _latest_poll(connection: psycopg.Connection, entry_id: int) -> tuple[str | None, int | None]:
    row = connection.execute(
        """
        SELECT polled_at, duration_ms
        FROM poll_history
        WHERE poll_entry_id = %s
        ORDER BY polled_at DESC, id DESC
        LIMIT 1
        """,
        (entry_id,),
    ).fetchone()
    if row is None:
        return None, None
    return _iso(_aware(row["polled_at"])), row["duration_ms"]


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
    day_from, day_to, range_start, range_end = _resolved_dates(day_from, day_to, now)
    window_start = now - timedelta(hours=WINDOWS[window])

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
    points, max_ms, slots = _graph(ordered, incidents, gaps)
    last = ordered[-1] if ordered else None
    open_incident = next((row for row in reversed(incidents) if row["end"] is None), None)
    return {
        "window": window,
        "percentage": None if not in_window else round(100 * successful / len(in_window), 1),
        "average_ms": None if not responded else int(round(sum(responded) / len(responded))),
        "graph": {"max_ms": max_ms, "slots": slots, "points": points},
        "from": day_from.isoformat(),
        "to": day_to.isoformat(),
        "page": page,
        "page_size": page_size,
        "total": total,
        "last_polled_at": _iso(last["polled_at"]) if last else None,
        "last_duration_ms": last["duration_ms"] if last else None,
        "open_incident_seconds": None if open_incident is None else open_incident["duration_seconds"],
        "rows": [_serialize_row(row) for row in visible],
    }


def _resolved_dates(
    day_from: date | None,
    day_to: date | None,
    now: datetime,
) -> tuple[date, date, datetime, datetime]:
    today = now.date()
    if day_from is None:
        day_from = today - timedelta(days=30)
    if day_to is None:
        day_to = today
    if day_from > day_to:
        raise EntryError("The start date must be on or before the end date.")
    range_start = datetime.combine(day_from, time.min, tzinfo=timezone.utc)
    range_end = datetime.combine(day_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return day_from, day_to, range_start, range_end


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


def incident_bounds(checks: list[dict], interval_seconds: int, now: datetime) -> list[dict]:
    """Same incidents as the statistics journal. end is None while one is open."""
    return _incidents(checks, interval_seconds, now)


def load_incident_bounds(
    connection: psycopg.Connection,
    entry_id: int,
    interval_seconds: int,
    now: datetime,
) -> list[dict]:
    """Incidents for the whole history, without loading every check into Python."""
    rows = _incident_rows(connection, entry_id, interval_seconds, bounded=False, range_start=now, range_end=now)
    for row in rows:
        row["duration_seconds"] = _duration(row["start"], row["end"], _aware(now))
    return rows


def _window_summary(
    connection: psycopg.Connection,
    entry_id: int,
    window_start: datetime,
    window_end: datetime,
) -> tuple[float | None, int | None]:
    row = connection.execute(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE message = 'OK') AS successful,
            AVG(duration_ms) FILTER (WHERE http_status IS NOT NULL) AS average_ms
        FROM poll_history
        WHERE poll_entry_id = %s AND polled_at >= %s AND polled_at <= %s
        """,
        (entry_id, window_start, window_end),
    ).fetchone()
    total = row["total"]
    percentage = None if not total else round(100 * row["successful"] / total, 1)
    average = row["average_ms"]
    average_ms = None if average is None else int(round(float(average)))
    return percentage, average_ms


def _recent_graph(
    connection: psycopg.Connection,
    entry_id: int,
    interval_seconds: int,
    now: datetime,
) -> tuple[list[dict], int, int]:
    rows = connection.execute(
        """
        SELECT id, polled_at, http_status, duration_ms, message
        FROM poll_history
        WHERE poll_entry_id = %s
        ORDER BY polled_at DESC, id DESC
        LIMIT %s
        """,
        (entry_id, GRAPH_CHECKS),
    ).fetchall()
    ordered = sorted(
        ({**row, "polled_at": _aware(row["polled_at"])} for row in rows),
        key=lambda row: (row["polled_at"], row["id"]),
    )
    incidents = _incidents(ordered, interval_seconds, now)
    gaps = _gaps(ordered, [], interval_seconds)
    return _graph(ordered, incidents, gaps)


def _journal(
    connection: psycopg.Connection,
    entry_id: int,
    interval_seconds: int,
    range_start: datetime,
    range_end: datetime,
    page: int,
    page_size: int,
    now: datetime,
) -> tuple[list[dict], int, int]:
    incidents, gaps = _journal_sources(
        connection,
        entry_id,
        interval_seconds,
        range_start,
        range_end,
    )
    rows = []
    for incident in incidents:
        if not _overlaps(incident, range_start, range_end):
            continue
        incident["duration_seconds"] = _duration(incident["start"], incident["end"], now)
        incident["reason"] = ", ".join(_group_label(group) for group in incident["groups"])
        rows.append(incident)
    rows.extend(gap for gap in gaps if _overlaps(gap, range_start, range_end))
    rows.sort(key=lambda row: row["start"], reverse=True)
    total = len(rows)
    page = clamp_page(page, page_size, total)
    start_index = (page - 1) * page_size
    visible = rows[start_index : start_index + page_size]
    return [_serialize_row(row) for row in visible], total, page


def _open_incident_seconds(
    connection: psycopg.Connection,
    entry_id: int,
    interval_seconds: int,
    now: datetime,
) -> int | None:
    latest = connection.execute(
        """
        SELECT polled_at, message
        FROM poll_history
        WHERE poll_entry_id = %s
        ORDER BY polled_at DESC, id DESC
        LIMIT 1
        """,
        (entry_id,),
    ).fetchone()
    if latest is None or latest["message"] == "OK":
        return None
    last_ok = connection.execute(
        """
        SELECT polled_at
        FROM poll_history
        WHERE poll_entry_id = %s AND message = 'OK' AND polled_at < %s
        ORDER BY polled_at DESC, id DESC
        LIMIT 1
        """,
        (entry_id, latest["polled_at"]),
    ).fetchone()
    range_start = _aware(last_ok["polled_at"]) if last_ok is not None else datetime.min.replace(tzinfo=timezone.utc)
    incidents = _incident_rows(
        connection,
        entry_id,
        interval_seconds,
        bounded=True,
        range_start=range_start,
        range_end=now + timedelta(seconds=1),
    )
    open_incident = next((row for row in reversed(incidents) if row["end"] is None), None)
    if open_incident is None:
        return None
    return _duration(open_incident["start"], None, now)


def _incident_rows(
    connection: psycopg.Connection,
    entry_id: int,
    interval_seconds: int,
    *,
    bounded: bool,
    range_start: datetime,
    range_end: datetime,
) -> list[dict]:
    rows = connection.execute(
        _INCIDENT_SQL,
        {
            "entry_id": entry_id,
            "bounded": bounded,
            "range_start": range_start,
            "range_end": range_end,
            "gap_seconds": _gap_seconds(interval_seconds),
        },
    ).fetchall()
    return [_incident_record(row) for row in rows]


def _journal_sources(
    connection: psycopg.Connection,
    entry_id: int,
    interval_seconds: int,
    range_start: datetime,
    range_end: datetime,
) -> tuple[list[dict], list[dict]]:
    """Incidents and gap bounds from one pass over the selected history."""
    rows = connection.execute(
        _SPAN_SQL,
        {
            "entry_id": entry_id,
            "bounded": True,
            "range_start": range_start,
            "range_end": range_end,
            "gap_seconds": _gap_seconds(interval_seconds),
        },
    ).fetchall()
    incidents = [_incident_record(row) for row in rows if row["kind"] == "incident"]
    pairs = [row for row in rows if row["kind"] == "gap"]
    return incidents, _labeled_gaps(connection, entry_id, interval_seconds, pairs)


def _incident_record(row: dict) -> dict:
    groups = row["groups"] or []
    return {
        "kind": "incident",
        "start": _aware(row["started_at"]),
        "end": None if row["ended_at"] is None else _aware(row["ended_at"]),
        "groups": [
            {
                "status": group["status"],
                "message": group["message"],
                "count": group["count"],
            }
            for group in groups
        ],
    }


def _labeled_gaps(
    connection: psycopg.Connection,
    entry_id: int,
    interval_seconds: int,
    pairs: list[dict],
) -> list[dict]:
    if not pairs:
        return []
    events = _events_between(
        connection,
        entry_id,
        min(_aware(row["started_at"]) for row in pairs),
        max(_aware(row["ended_at"]) for row in pairs),
    )
    found: list[dict] = []
    for row in pairs:
        found.extend(
            _gap_segments(
                _aware(row["started_at"]),
                _aware(row["ended_at"]),
                interval_seconds,
                events,
            )
        )
    return found


def _events_between(
    connection: psycopg.Connection,
    entry_id: int,
    event_from: datetime,
    event_to: datetime,
) -> list[dict]:
    anchor = connection.execute(
        """
        SELECT id, kind, happened_at
        FROM poll_entry_events
        WHERE poll_entry_id = %s AND happened_at <= %s
        ORDER BY happened_at DESC, id DESC
        LIMIT 1
        """,
        (entry_id, event_from),
    ).fetchone()
    later = connection.execute(
        """
        SELECT id, kind, happened_at
        FROM poll_entry_events
        WHERE poll_entry_id = %s AND happened_at > %s AND happened_at <= %s
        ORDER BY happened_at, id
        """,
        (entry_id, event_from, event_to),
    ).fetchall()
    rows = []
    if anchor is not None:
        rows.append(dict(anchor))
    rows.extend(dict(row) for row in later)
    for row in rows:
        row["happened_at"] = _aware(row["happened_at"])
    return rows


def _gap_seconds(interval_seconds: int) -> float:
    return 2 * interval_seconds + GAP_EXTRA_SECONDS


_CHECKS_CTE = """
WITH before_row AS (
    SELECT id, polled_at, http_status, message
    FROM poll_history
    WHERE poll_entry_id = %(entry_id)s
      AND %(bounded)s
      AND polled_at < %(range_start)s
    ORDER BY polled_at DESC, id DESC
    LIMIT 1
),
after_row AS (
    SELECT id, polled_at, http_status, message
    FROM poll_history
    WHERE poll_entry_id = %(entry_id)s
      AND %(bounded)s
      AND polled_at >= %(range_end)s
    ORDER BY polled_at, id
    LIMIT 1
),
checks AS (
    SELECT id, polled_at, http_status, message FROM before_row
    UNION ALL
    SELECT id, polled_at, http_status, message
    FROM poll_history
    WHERE poll_entry_id = %(entry_id)s
      AND (
          NOT %(bounded)s
          OR (polled_at >= %(range_start)s AND polled_at < %(range_end)s)
      )
    UNION ALL
    SELECT id, polled_at, http_status, message FROM after_row
),
ordered AS (
    SELECT
        id,
        polled_at,
        http_status,
        message,
        lag(polled_at) OVER w AS prev_at,
        lag(message) OVER w AS prev_message,
        lead(polled_at) OVER w AS next_at,
        lead(message) OVER w AS next_message
    FROM checks
    WINDOW w AS (ORDER BY polled_at, id)
)
"""

_INCIDENT_SQL = (
    _CHECKS_CTE
    + """
,
failures AS (
    SELECT
        id,
        polled_at,
        http_status,
        message,
        next_at,
        next_message,
        SUM(
            CASE
                WHEN prev_at IS NULL
                  OR prev_message = 'OK'
                  OR EXTRACT(EPOCH FROM (polled_at - prev_at)) >= %(gap_seconds)s
                THEN 1
                ELSE 0
            END
        ) OVER (ORDER BY polled_at, id) AS run_id
    FROM ordered
    WHERE message <> 'OK'
),
runs AS (
    SELECT
        run_id,
        MIN(polled_at) AS started_at,
        MAX(polled_at) AS last_at,
        (ARRAY_AGG(next_at ORDER BY polled_at DESC, id DESC))[1] AS next_at,
        (ARRAY_AGG(next_message ORDER BY polled_at DESC, id DESC))[1] AS next_message
    FROM failures
    GROUP BY run_id
    HAVING COUNT(*) >= 2
)
SELECT
    runs.started_at,
    CASE
        WHEN runs.next_message = 'OK'
         AND EXTRACT(EPOCH FROM (runs.next_at - runs.last_at)) < %(gap_seconds)s
        THEN runs.next_at
        WHEN runs.next_at IS NOT NULL THEN runs.last_at
        ELSE NULL
    END AS ended_at,
    (
        SELECT jsonb_agg(
            jsonb_build_object(
                'status', grouped.http_status,
                'message', grouped.message,
                'count', grouped.count
            )
            ORDER BY grouped.first_id
        )
        FROM (
            SELECT
                http_status,
                message,
                COUNT(*) AS count,
                MIN(id) AS first_id
            FROM failures
            WHERE failures.run_id = runs.run_id
            GROUP BY http_status, message
        ) AS grouped
    ) AS groups
FROM runs
"""
)

_SPAN_SQL = """
WITH before_row AS (
    SELECT id, polled_at, http_status, message
    FROM poll_history
    WHERE poll_entry_id = %(entry_id)s
      AND %(bounded)s
      AND polled_at < %(range_start)s
    ORDER BY polled_at DESC, id DESC
    LIMIT 1
),
after_row AS (
    SELECT id, polled_at, http_status, message
    FROM poll_history
    WHERE poll_entry_id = %(entry_id)s
      AND %(bounded)s
      AND polled_at >= %(range_end)s
    ORDER BY polled_at, id
    LIMIT 1
),
checks AS (
    SELECT id, polled_at, http_status, message FROM before_row
    UNION ALL
    SELECT id, polled_at, http_status, message
    FROM poll_history
    WHERE poll_entry_id = %(entry_id)s
      AND (
          NOT %(bounded)s
          OR (polled_at >= %(range_start)s AND polled_at < %(range_end)s)
      )
    UNION ALL
    SELECT id, polled_at, http_status, message FROM after_row
),
ordered AS MATERIALIZED (
    SELECT
        id,
        polled_at,
        http_status,
        message,
        lag(polled_at) OVER w AS prev_at,
        lag(message) OVER w AS prev_message,
        lead(polled_at) OVER w AS next_at,
        lead(message) OVER w AS next_message
    FROM checks
    WINDOW w AS (ORDER BY polled_at, id)
),
failures AS (
    SELECT
        id,
        polled_at,
        http_status,
        message,
        next_at,
        next_message,
        SUM(
            CASE
                WHEN prev_at IS NULL
                  OR prev_message = 'OK'
                  OR EXTRACT(EPOCH FROM (polled_at - prev_at)) >= %(gap_seconds)s
                THEN 1
                ELSE 0
            END
        ) OVER (ORDER BY polled_at, id) AS run_id
    FROM ordered
    WHERE message <> 'OK'
),
runs AS (
    SELECT
        run_id,
        MIN(polled_at) AS started_at,
        MAX(polled_at) AS last_at,
        (ARRAY_AGG(next_at ORDER BY polled_at DESC, id DESC))[1] AS next_at,
        (ARRAY_AGG(next_message ORDER BY polled_at DESC, id DESC))[1] AS next_message
    FROM failures
    GROUP BY run_id
    HAVING COUNT(*) >= 2
)
SELECT
    'incident' AS kind,
    runs.started_at,
    CASE
        WHEN runs.next_message = 'OK'
         AND EXTRACT(EPOCH FROM (runs.next_at - runs.last_at)) < %(gap_seconds)s
        THEN runs.next_at
        WHEN runs.next_at IS NOT NULL THEN runs.last_at
        ELSE NULL
    END AS ended_at,
    (
        SELECT jsonb_agg(
            jsonb_build_object(
                'status', grouped.http_status,
                'message', grouped.message,
                'count', grouped.count
            )
            ORDER BY grouped.first_id
        )
        FROM (
            SELECT
                http_status,
                message,
                COUNT(*) AS count,
                MIN(id) AS first_id
            FROM failures
            WHERE failures.run_id = runs.run_id
            GROUP BY http_status, message
        ) AS grouped
    ) AS groups
FROM runs
UNION ALL
SELECT
    'gap' AS kind,
    prev_at AS started_at,
    polled_at AS ended_at,
    NULL AS groups
FROM ordered
WHERE prev_at IS NOT NULL
  AND EXTRACT(EPOCH FROM (polled_at - prev_at)) >= %(gap_seconds)s
"""


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
) -> tuple[list[dict], int, int]:
    """One point per recent check. Timeouts stay off the line and keep their slot."""
    series = checks[-GRAPH_CHECKS:]
    points: list[dict] = []
    for slot, row in enumerate(series):
        if row["http_status"] is None:
            continue
        at = row["polled_at"]
        previous = points[-1]["at"] if points else None
        connect = previous is not None and not _crosses(previous, at, incidents, gaps)
        points.append(
            {
                "slot": slot,
                "ms": int(row["duration_ms"]),
                "connect": connect,
                "at": at,
            }
        )
    peak = max((point["ms"] for point in points), default=0)
    serialized = [
        {"slot": point["slot"], "ms": point["ms"], "connect": point["connect"]}
        for point in points
    ]
    return serialized, max(1000, peak), len(series)


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
