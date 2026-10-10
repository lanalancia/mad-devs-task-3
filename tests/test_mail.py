import unittest
from datetime import datetime, timedelta, timezone

from backend.mail import letter_plan, maintenance_status, merge_windows, started_message, ended_message


def at(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


class MaintenanceStatusTests(unittest.TestCase):
    def test_not_started_before_the_window(self):
        now = at("2026-10-10T12:00:00Z")
        status = maintenance_status(now + timedelta(hours=1), now + timedelta(hours=2), True, now)
        self.assertEqual(status, "NOT_STARTED")

    def test_ended_wins_after_a_down_poll(self):
        now = at("2026-10-10T14:00:00Z")
        status = maintenance_status(now - timedelta(hours=2), now - timedelta(hours=1), True, now)
        self.assertEqual(status, "ENDED")

    def test_active_window_uses_the_down_poll(self):
        now = at("2026-10-10T12:00:00Z")
        start = now - timedelta(minutes=30)
        end = now + timedelta(minutes=30)
        self.assertEqual(maintenance_status(start, end, False, now), "STARTED_AND_UP")
        self.assertEqual(maintenance_status(start, end, True, now), "STARTED_AND_DOWN")


class MergeWindowTests(unittest.TestCase):
    def test_same_minute_boundary_is_one_stretch(self):
        windows = [
            (at("2026-10-10T10:00:00Z"), at("2026-10-10T12:00:00Z")),
            (at("2026-10-10T12:00:30Z"), at("2026-10-10T13:00:00Z")),
        ]
        self.assertEqual(
            merge_windows(windows),
            [(at("2026-10-10T10:00:00Z"), at("2026-10-10T13:00:00Z"))],
        )

    def test_a_later_minute_stays_a_gap(self):
        windows = [
            (at("2026-10-10T10:00:00Z"), at("2026-10-10T12:00:00Z")),
            (at("2026-10-10T12:01:00Z"), at("2026-10-10T13:00:00Z")),
        ]
        self.assertEqual(merge_windows(windows), windows)


class LetterPlanTests(unittest.TestCase):
    def test_edges_outside_a_window_send_on_the_incident(self):
        start = at("2026-10-10T09:00:00Z")
        end = at("2026-10-10T15:00:00Z")
        window = [(at("2026-10-10T10:00:00Z"), at("2026-10-10T12:00:00Z"))]
        plan = letter_plan(start, end, window, end)
        self.assertEqual(plan, {"started": "send", "ended": "send"})

    def test_both_edges_inside_a_finished_window_are_skipped(self):
        window = [(at("2026-10-10T10:00:00Z"), at("2026-10-10T13:00:00Z"))]
        plan = letter_plan(
            at("2026-10-10T10:30:00Z"),
            at("2026-10-10T12:30:00Z"),
            window,
            at("2026-10-10T14:00:00Z"),
        )
        self.assertEqual(plan, {"started": "skip", "ended": "skip"})

    def test_recovery_during_the_window_waits_for_the_end(self):
        window = [(at("2026-10-10T10:00:00Z"), at("2026-10-10T13:00:00Z"))]
        start = at("2026-10-10T09:00:00Z")
        end = at("2026-10-10T11:00:00Z")
        while_open = letter_plan(start, end, window, at("2026-10-10T12:00:00Z"))
        after = letter_plan(start, end, window, at("2026-10-10T13:00:00Z"))
        self.assertEqual(while_open, {"started": "send", "ended": "wait"})
        self.assertEqual(after, {"started": "send", "ended": "send"})

    def test_a_start_inside_the_window_is_sent_when_the_window_ends(self):
        window = [(at("2026-10-10T10:00:00Z"), at("2026-10-10T13:00:00Z"))]
        start = at("2026-10-10T10:30:00Z")
        waiting = letter_plan(start, None, window, at("2026-10-10T12:00:00Z"))
        due = letter_plan(start, None, window, at("2026-10-10T13:00:00Z"))
        self.assertEqual(waiting["started"], "wait")
        self.assertEqual(due, {"started": "send", "ended": "wait"})

    def test_overlapping_windows_are_judged_as_one_stretch(self):
        windows = [
            (at("2026-10-10T10:00:00Z"), at("2026-10-10T12:00:00Z")),
            (at("2026-10-10T11:00:00Z"), at("2026-10-10T13:00:00Z")),
        ]
        start = at("2026-10-10T10:30:00Z")
        at_noon = letter_plan(start, None, windows, at("2026-10-10T12:30:00Z"))
        at_end = letter_plan(start, None, windows, at("2026-10-10T13:00:00Z"))
        covered = letter_plan(start, at("2026-10-10T12:30:00Z"), windows, at("2026-10-10T13:00:00Z"))
        self.assertEqual(at_noon["started"], "wait")
        self.assertEqual(at_end["started"], "send")
        self.assertEqual(covered, {"started": "skip", "ended": "skip"})

    def test_a_gap_releases_the_letter_at_the_first_window(self):
        windows = [
            (at("2026-10-10T10:00:00Z"), at("2026-10-10T11:00:00Z")),
            (at("2026-10-10T12:00:00Z"), at("2026-10-10T13:00:00Z")),
        ]
        plan = letter_plan(
            at("2026-10-10T10:30:00Z"),
            None,
            windows,
            at("2026-10-10T11:30:00Z"),
        )
        self.assertEqual(plan["started"], "send")


class MessageTests(unittest.TestCase):
    def test_messages_use_the_incident_edges(self):
        start = at("2026-10-10T10:30:00Z")
        end = at("2026-10-10T12:30:45Z")
        self.assertEqual(
            started_message("http://example.test", start),
            "http://example.test downtime incident started at 2026-10-10 10:30:00 UTC.",
        )
        self.assertEqual(
            ended_message("http://example.test", start, end),
            "http://example.test downtime incident ended. "
            "It was started at 2026-10-10 10:30:00 UTC and ended at 2026-10-10 12:30:45 UTC.",
        )
