import asyncio
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from backend.db import DatabaseError, connect, ensure_schema
from backend.entries import delete_entry, load_page, load_poll_target, save_new_entry, update_entry
from backend.poll_control import PollControl, run_poll
from backend.polling import HistoryRow

URL = "http://example.test/step3-entry"


def database():
    try:
        connection = connect()
    except DatabaseError as exc:
        raise unittest.SkipTest(f"Database is not available: {exc}") from exc
    try:
        ensure_schema(connection)
    except DatabaseError as exc:
        connection.close()
        raise unittest.SkipTest(f"Schema is not available: {exc}") from exc
    connection.autocommit = False
    connection.execute("SELECT 1")
    return connection


class EntryDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.connection = database()

    def tearDown(self):
        self.connection.rollback()
        self.connection.close()

    def test_create_edit_delete_and_restore_keep_history(self):
        action, page = save_new_entry(self.connection, URL, 45, 7, 1, 100)
        self.assertEqual(action, "create")
        created = next(entry for entry in page["entries"] if entry["url"] == URL)
        self.assertEqual(created["status"], "PAUSED")
        self.assertEqual(created["interval_seconds"], 45)
        self.assertEqual(created["timeout_seconds"], 7)
        self.assertEqual(created["expected_code"], 200)
        self.assertEqual(page["page"], 1)
        self.assertEqual(page["page_size"], 100)

        entry_id = created["id"]
        self.connection.execute(
            """
            INSERT INTO poll_history (poll_entry_id, polled_at, http_status, duration_ms, message)
            VALUES (%s, '2026-10-09T12:00:00Z', 200, 10, 'OK')
            """,
            (entry_id,),
        )

        updated = update_entry(self.connection, URL, 45, 7, "ACTIVE", 1, 100, expected_code=418)
        self.assertIsNotNone(updated)
        self.assertEqual(self.event_kinds(entry_id), ["resumed"])
        active = next(entry for entry in updated["entries"] if entry["url"] == URL)
        self.assertEqual(active["status"], "ACTIVE")
        self.assertEqual(active["expected_code"], 418)
        self.assertEqual(active["health"], "UP")
        self.assertEqual(active["error"], "")
        self.assertEqual(active["last_polled_at"], "2026-10-09T12:00:00Z")

        hidden = delete_entry(self.connection, URL, 1, 100)
        self.assertIsNotNone(hidden)
        self.assertEqual(self.event_kinds(entry_id), ["resumed", "deleted"])
        self.assertNotIn(URL, [entry["url"] for entry in hidden["entries"]])
        history = self.connection.execute(
            "SELECT COUNT(*) AS total FROM poll_history WHERE poll_entry_id = %s",
            (entry_id,),
        ).fetchone()
        self.assertEqual(history["total"], 1)

        restored_action, restored = save_new_entry(
            self.connection, URL, 30, 5, 1, 100, expected_code=204
        )
        self.assertEqual(restored_action, "restore")
        again = next(entry for entry in restored["entries"] if entry["url"] == URL)
        self.assertEqual(again["id"], entry_id)
        self.assertEqual(again["status"], "PAUSED")
        self.assertEqual(again["interval_seconds"], 30)
        self.assertEqual(again["timeout_seconds"], 5)
        self.assertEqual(again["expected_code"], 204)
        self.assertEqual(again["health"], "UP")
        self.assertEqual(self.event_kinds(entry_id), ["resumed", "deleted", "restored"])

        duplicate, no_page = save_new_entry(self.connection, URL, 30, 5, 1, 100)
        self.assertEqual(duplicate, "exists")
        self.assertIsNone(no_page)
        visible = load_page(self.connection, 1, 100)
        ids = [entry["id"] for entry in visible["entries"]]
        self.assertEqual(ids.count(entry_id), 1)

    def test_poll_now_includes_a_paused_url_and_leaves_it_paused(self):
        url = "http://example.test/step6-poll"
        _action, page = save_new_entry(self.connection, url, 60, 5, 1, 100, expected_code=201)
        created = next(entry for entry in page["entries"] if entry["url"] == url)
        target = load_poll_target(self.connection, created["id"])
        self.assertEqual(target["status"], "PAUSED")
        self.assertEqual(target["expected_code"], 201)
        control = PollControl()
        started = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
        with patch(
            "backend.poll_control.run_cycle",
            return_value=(started, 15, HistoryRow(http_status=201, message="OK")),
        ):
            asyncio.run(run_poll(self.connection, target, control))
        status = self.connection.execute(
            "SELECT status FROM poll_entries WHERE id = %s",
            (created["id"],),
        ).fetchone()
        self.assertEqual(status["status"], "PAUSED")
        saved = self.connection.execute(
            """
            SELECT http_status, message
            FROM poll_history
            WHERE poll_entry_id = %s
            """,
            (created["id"],),
        ).fetchone()
        self.assertEqual(saved["http_status"], 201)
        self.assertEqual(saved["message"], "OK")
        self.assertEqual(control.running_ids(), set())
        delete_entry(self.connection, url, 1, 100)
        self.assertIsNone(load_poll_target(self.connection, created["id"]))

    def event_kinds(self, entry_id: int) -> list[str]:
        rows = self.connection.execute(
            """
            SELECT kind
            FROM poll_entry_events
            WHERE poll_entry_id = %s
            ORDER BY id
            """,
            (entry_id,),
        ).fetchall()
        return [row["kind"] for row in rows]
