import unittest
from datetime import datetime, timedelta, timezone

from backend.entries import EntryError
from backend.stats import build_statistics

BASE = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
NOW = BASE + timedelta(hours=1)
INTERVAL = 30


def at(seconds):
    return BASE + timedelta(seconds=seconds)


def check(seconds, message="OK", status=200, duration=100):
    return {
        "polled_at": at(seconds),
        "message": message,
        "http_status": status,
        "duration_ms": duration,
    }


def event(seconds, kind):
    return {"happened_at": at(seconds), "kind": kind}


def report(checks, events=None, **overrides):
    values = {
        "checks": checks,
        "events": events or [],
        "interval_seconds": INTERVAL,
        "window": "day",
        "day_from": BASE.date(),
        "day_to": BASE.date(),
        "page": 1,
        "page_size": 10,
        "now": NOW,
    }
    values.update(overrides)
    return build_statistics(**values)


class IncidentTests(unittest.TestCase):
    def test_one_failure_is_not_an_incident_but_counts_in_the_percentage(self):
        result = report([check(0), check(30, "404", 404, 40), check(60)])
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["percentage"], 66.7)
        self.assertEqual(result["last_polled_at"], "2026-10-10T12:01:00Z")

    def test_different_errors_between_ok_results_are_one_incident(self):
        result = report(
            [
                check(0),
                check(30, "404", 404, 40),
                check(60, "Down detected", None, 5000),
                check(90),
            ]
        )
        self.assertEqual(len(result["rows"]), 1)
        incident = result["rows"][0]
        self.assertEqual(incident["kind"], "incident")
        self.assertEqual(incident["start"], "2026-10-10T12:00:30Z")
        self.assertEqual(incident["end"], "2026-10-10T12:01:30Z")
        self.assertEqual(incident["duration_seconds"], 60)
        self.assertEqual(
            incident["groups"],
            [
                {"status": 404, "message": "404", "count": 1},
                {"status": None, "message": "Down detected", "count": 1},
            ],
        )

    def test_an_outage_without_recovery_stays_open(self):
        result = report([check(0), check(30, "404", 404), check(60, "500", 500)])
        incident = result["rows"][0]
        self.assertIsNone(incident["end"])
        self.assertEqual(incident["duration_seconds"], int((NOW - at(30)).total_seconds()))


class GapTests(unittest.TestCase):
    def test_gap_shorter_than_one_skipped_poll_plus_a_minute_is_kept(self):
        result = report([check(0), check(119)])
        self.assertEqual(result["rows"], [])

    def test_a_long_gap_without_events_is_server_down(self):
        result = report([check(0), check(10000)])
        self.assertEqual(len(result["rows"]), 1)
        gap = result["rows"][0]
        self.assertEqual(gap["kind"], "no_data")
        self.assertEqual(gap["reason"], "Server was down")
        self.assertEqual(gap["start"], "2026-10-10T12:00:00Z")
        self.assertEqual(gap["end"], "2026-10-10T14:46:40Z")

    def test_pause_and_delete_split_the_gap(self):
        result = report(
            [check(0), check(10000)],
            [
                event(10, "deleted"),
                event(4000, "restored"),
                event(9900, "resumed"),
            ],
        )
        reasons = [row["reason"] for row in result["rows"]]
        self.assertEqual(reasons, ["polling was paused", "entry was deactivated"])
        self.assertNotIn("Server was down", reasons)

    def test_timeouts_are_left_off_the_graph_and_out_of_the_average(self):
        result = report(
            [
                check(0, duration=100),
                check(1800, "Down detected", None, 5000),
                check(3600, duration=300),
            ]
        )
        self.assertEqual(result["average_ms"], 200)
        self.assertEqual(result["percentage"], 66.7)
        self.assertEqual(len(result["graph"]["points"]), 2)
        self.assertFalse(result["graph"]["points"][1]["connect"])
        self.assertEqual(result["graph"]["max_ms"], 1000)

    def test_the_line_breaks_across_an_incident(self):
        result = report(
            [
                check(0, duration=80),
                check(100, "404", 404, 400),
                check(200, "500", 500, 500),
                check(300, duration=90),
            ]
        )
        self.assertEqual(len(result["graph"]["points"]), 2)
        self.assertFalse(result["graph"]["points"][1]["connect"])

    def test_a_point_above_1000_ms_raises_the_scale(self):
        result = report([check(0, duration=2500)])
        self.assertEqual(result["graph"]["max_ms"], 2500)

    def test_the_date_range_has_to_run_forward(self):
        with self.assertRaises(EntryError):
            report([check(0)], day_from=BASE.date(), day_to=BASE.date() - timedelta(days=1))
