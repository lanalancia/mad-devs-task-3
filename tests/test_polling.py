import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from backend.polling import Attempt, finalize, format_console, is_due, is_timeout, run_cycle


class FinalizeTests(unittest.TestCase):
    def test_expected_code_is_ok(self):
        row = finalize(Attempt("http", http_status=200), 200, is_retry=False)
        self.assertIsNotNone(row)
        self.assertEqual(row.http_status, 200)
        self.assertEqual(row.message, "OK")

    def test_other_code_is_stored_without_a_retry(self):
        row = finalize(Attempt("http", http_status=404), 200, is_retry=False)
        self.assertIsNotNone(row)
        self.assertEqual(row.http_status, 404)
        self.assertEqual(row.message, "404")

    def test_first_timeout_is_not_stored(self):
        self.assertIsNone(finalize(Attempt("timeout"), 200, is_retry=False))

    def test_second_timeout_is_down_detected(self):
        row = finalize(Attempt("timeout"), 200, is_retry=True)
        self.assertIsNotNone(row)
        self.assertIsNone(row.http_status)
        self.assertEqual(row.message, "Down detected")

    def test_connection_error_is_stored_on_the_first_attempt(self):
        row = finalize(
            Attempt("error", error="[Errno 11001] getaddrinfo failed"),
            200,
            is_retry=False,
        )
        self.assertIsNotNone(row)
        self.assertIsNone(row.http_status)
        self.assertEqual(row.message, "[Errno 11001] getaddrinfo failed")


class CycleTests(unittest.TestCase):
    def test_a_timeout_is_sent_a_second_time_and_then_stored(self):
        with patch("backend.polling.request_once", return_value=Attempt("timeout")) as request:
            _started, _duration, row = run_cycle("http://example.test", 5, 200)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(row.message, "Down detected")
        self.assertIsNone(row.http_status)

    def test_a_connection_error_is_not_retried(self):
        attempt = Attempt("error", error="[Errno 11001] getaddrinfo failed")
        with patch("backend.polling.request_once", return_value=attempt) as request:
            _started, _duration, row = run_cycle("http://example.test", 5, 200)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(row.message, "[Errno 11001] getaddrinfo failed")

    def test_a_successful_retry_stores_the_second_response(self):
        attempts = [Attempt("timeout"), Attempt("http", http_status=200)]
        with patch("backend.polling.request_once", side_effect=attempts) as request:
            _started, _duration, row = run_cycle("https://www.google.com", 5, 200)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(row.http_status, 200)
        self.assertEqual(row.message, "OK")


class ScheduleTests(unittest.TestCase):
    def test_missing_history_is_due_immediately(self):
        now = datetime(2026, 10, 9, tzinfo=timezone.utc)
        self.assertTrue(is_due(None, 30, now))

    def test_next_poll_is_counted_from_the_request_start(self):
        started = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)
        self.assertFalse(is_due(started, 30, started + timedelta(seconds=2)))
        self.assertFalse(is_due(started, 30, started + timedelta(seconds=29)))
        self.assertTrue(is_due(started, 30, started + timedelta(seconds=30)))


class ConsoleTests(unittest.TestCase):
    def test_format_includes_the_saved_status_and_message(self):
        self.assertEqual(
            format_console("https://www.google.com", 200, "OK"),
            "Requesting https://www.google.com, response status: 200, message: OK",
        )

    def test_missing_status_is_a_dash(self):
        self.assertEqual(
            format_console("http://example.test", None, "Down detected"),
            "Requesting http://example.test, response status: -, message: Down detected",
        )


class TimeoutTests(unittest.TestCase):
    def test_timeout_error(self):
        self.assertTrue(is_timeout(TimeoutError("The read operation timed out")))

    def test_dns_error_is_not_a_timeout(self):
        self.assertFalse(is_timeout(OSError("getaddrinfo failed")))


if __name__ == "__main__":
    unittest.main()
