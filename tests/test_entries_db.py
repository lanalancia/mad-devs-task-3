import unittest

from backend.db import DatabaseError, connect, ensure_schema
from backend.entries import delete_entry, load_page, save_new_entry, update_entry

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

        updated = update_entry(self.connection, URL, 45, 7, "ACTIVE", 1, 100)
        self.assertIsNotNone(updated)
        active = next(entry for entry in updated["entries"] if entry["url"] == URL)
        self.assertEqual(active["status"], "ACTIVE")
        self.assertEqual(active["health"], "UP")
        self.assertEqual(active["error"], "")
        self.assertEqual(active["last_polled_at"], "2026-10-09T12:00:00Z")

        hidden = delete_entry(self.connection, URL, 1, 100)
        self.assertIsNotNone(hidden)
        self.assertNotIn(URL, [entry["url"] for entry in hidden["entries"]])
        history = self.connection.execute(
            "SELECT COUNT(*) AS total FROM poll_history WHERE poll_entry_id = %s",
            (entry_id,),
        ).fetchone()
        self.assertEqual(history["total"], 1)

        restored_action, restored = save_new_entry(self.connection, URL, 30, 5, 1, 100)
        self.assertEqual(restored_action, "restore")
        again = next(entry for entry in restored["entries"] if entry["url"] == URL)
        self.assertEqual(again["id"], entry_id)
        self.assertEqual(again["status"], "PAUSED")
        self.assertEqual(again["interval_seconds"], 30)
        self.assertEqual(again["timeout_seconds"], 5)
        self.assertEqual(again["health"], "UP")

        duplicate, no_page = save_new_entry(self.connection, URL, 30, 5, 1, 100)
        self.assertEqual(duplicate, "exists")
        self.assertIsNone(no_page)
        visible = load_page(self.connection, 1, 100)
        ids = [entry["id"] for entry in visible["entries"]]
        self.assertEqual(ids.count(entry_id), 1)
