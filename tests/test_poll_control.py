import asyncio
import threading
import unittest
from unittest.mock import patch

from backend.entries import EntryError
from backend.poll_control import ALREADY_POLLING, PollControl


ENTRY = {"id": 7, "url": "http://example.test", "timeout_seconds": 1, "expected_code": 200}


class PollControlTests(unittest.TestCase):
    def test_a_second_request_is_refused_without_a_scheduler(self):
        control = PollControl()
        self.assertTrue(control.claim(ENTRY["id"]))
        self.assertFalse(control.request_now(ENTRY))
        self.assertIn("waiting for a response", ALREADY_POLLING)

    def test_request_now_releases_the_claim_when_polling_is_not_running(self):
        control = PollControl()
        with self.assertRaises(EntryError):
            control.request_now(ENTRY)
        self.assertTrue(control.claim(ENTRY["id"]))

    def test_only_one_poll_is_started_for_a_url(self):
        control = PollControl()
        started = threading.Event()
        finished = threading.Event()
        blocker = asyncio.Event()

        async def fake(_connection, row, gate):
            started.set()
            await blocker.wait()
            gate.release(row["id"])
            finished.set()

        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_forever, daemon=True)
        with patch("backend.poll_control.run_poll", fake):
            thread.start()
            control.attach(loop, object())
            try:
                self.assertTrue(control.request_now(ENTRY))
                self.assertTrue(started.wait(2))
                self.assertFalse(control.request_now(ENTRY))
                loop.call_soon_threadsafe(blocker.set)
                self.assertTrue(finished.wait(2))
            finally:
                loop.call_soon_threadsafe(loop.stop)
                thread.join(2)
        self.assertTrue(control.claim(ENTRY["id"]))
