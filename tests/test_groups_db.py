import unittest
import uuid

from backend.db import DatabaseError, connect, ensure_schema, load_active_entries
from backend.entries import assign_group, delete_entry, save_new_entry, update_entry
from backend.groups import (
    GroupError,
    create_group,
    delete_group,
    save_email,
    update_email,
    update_group,
)


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


class GroupDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.connection = database()
        suffix = uuid.uuid4().hex[:8]
        self.url = f"http://example.test/step5-{suffix}"
        self.name = f"step5-{suffix}"

    def tearDown(self):
        self.connection.rollback()
        self.connection.close()

    def test_group_pause_keeps_the_url_pause_and_stops_polling(self):
        created = create_group(self.connection, self.name)
        group = next(item for item in created["groups"] if item["name"] == self.name)
        self.assertFalse(group["paused"])
        self.assertEqual(group["response_status"], "EMPTY")
        self.assertEqual(group["health"], "NO_DATA_YET")
        self.assertEqual(group["url_count"], 0)

        save_new_entry(self.connection, self.url, 30, 5, 1, 100)
        assigned = assign_group(self.connection, self.url, group["id"], 1, 100)
        entry = next(item for item in assigned["entries"] if item["url"] == self.url)
        self.assertEqual(entry["group_id"], group["id"])
        self.assertEqual(entry["poll_state"], "URL_PAUSED")
        self.assertEqual(entry["status"], "PAUSED")

        paused_urls = update_group(self.connection, group["id"], None, False)
        visible = next(item for item in paused_urls["groups"] if item["id"] == group["id"])
        self.assertEqual(visible["response_status"], "URLS_PAUSED")
        self.assertEqual(visible["url_count"], 1)

        update_entry(self.connection, self.url, 30, 5, "ACTIVE", 1, 100)
        self.connection.execute(
            """
            INSERT INTO poll_history (poll_entry_id, polled_at, http_status, duration_ms, message)
            VALUES (%s, '2026-10-10T12:00:00Z', 200, 12, 'OK')
            """,
            (entry["id"],),
        )
        polling = update_group(self.connection, group["id"], None, False)
        healthy = next(item for item in polling["groups"] if item["id"] == group["id"])
        self.assertEqual(healthy["response_status"], "POLLING")
        self.assertEqual(healthy["health"], "UP")

        held = update_group(self.connection, group["id"], None, True)
        stopped = next(item for item in held["groups"] if item["id"] == group["id"])
        self.assertEqual(stopped["response_status"], "GROUP_PAUSED")
        self.assertEqual(stopped["health"], "NO_DATA_YET")
        active_ids = {row["id"] for row in load_active_entries(self.connection)}
        self.assertNotIn(entry["id"], active_ids)

        resumed = update_entry(self.connection, self.url, 30, 5, "PAUSED", 1, 100)
        own = next(item for item in resumed["entries"] if item["url"] == self.url)
        self.assertEqual(own["poll_state"], "URL_PAUSED")
        released = update_group(self.connection, group["id"], None, False)
        both = next(item for item in released["groups"] if item["id"] == group["id"])
        self.assertEqual(both["response_status"], "URLS_PAUSED")

    def test_deleting_a_url_keeps_its_group_and_deleting_the_group_clears_it(self):
        created = create_group(self.connection, self.name)
        group_id = next(item["id"] for item in created["groups"] if item["name"] == self.name)
        save_new_entry(self.connection, self.url, 30, 5, 1, 100)
        assign_group(self.connection, self.url, group_id, 1, 100)
        delete_entry(self.connection, self.url, 1, 100)
        stored = self.connection.execute(
            "SELECT group_id, status FROM poll_entries WHERE url = %s",
            (self.url,),
        ).fetchone()
        self.assertEqual(stored["status"], "DELETED")
        self.assertEqual(stored["group_id"], group_id)
        counted = next(
            item["url_count"]
            for item in update_group(self.connection, group_id, self.name, None)["groups"]
            if item["id"] == group_id
        )
        self.assertEqual(counted, 0)

        delete_group(self.connection, group_id)
        cleared = self.connection.execute(
            "SELECT group_id FROM poll_entries WHERE url = %s",
            (self.url,),
        ).fetchone()
        self.assertIsNone(cleared["group_id"])

    def test_names_and_emails_reject_duplicates(self):
        create_group(self.connection, self.name)
        with self.assertRaises(GroupError):
            create_group(self.connection, self.name)
        group_id = self.connection.execute(
            "SELECT id FROM poll_groups WHERE name = %s",
            (self.name,),
        ).fetchone()["id"]
        save_email(self.connection, group_id, "ops@example.com")
        with self.assertRaises(GroupError):
            save_email(self.connection, group_id, "OPS@example.com")
        email_id = self.connection.execute(
            "SELECT id FROM poll_group_emails WHERE poll_group_id = %s",
            (group_id,),
        ).fetchone()["id"]
        updated = update_email(self.connection, email_id, "night@example.com")
        addresses = next(item["emails"] for item in updated["groups"] if item["id"] == group_id)
        self.assertEqual(addresses, [{"id": email_id, "address": "night@example.com"}])
