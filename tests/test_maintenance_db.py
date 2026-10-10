import unittest
import uuid
from datetime import datetime, timedelta, timezone

from backend.db import DatabaseError, connect, ensure_schema
from backend.entries import assign_group, save_new_entry
from backend.groups import create_group, save_email
from backend.mail import maintenance_status
from backend.maintenance import (
    MaintenanceError,
    create_maintenance,
    delete_maintenance,
    list_mails,
    reconcile_entry,
    require_timestamp,
)


def database():
    try:
        connection = connect()
        connection.execute("SET lock_timeout = '3s'")
    except DatabaseError as exc:
        raise unittest.SkipTest(f"Database is not available: {exc}") from exc
    try:
        ensure_schema(connection)
    except DatabaseError as exc:
        connection.close()
        raise unittest.SkipTest(f"Schema is not available: {exc}") from exc
    except Exception as exc:
        connection.close()
        raise unittest.SkipTest(f"Schema is not available: {exc}") from exc
    connection.autocommit = False
    connection.execute("SELECT 1")
    return connection


def at(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


class MaintenanceDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.connection = database()
        suffix = uuid.uuid4().hex[:8]
        self.url = f"http://example.test/step8-{suffix}"
        self.name = f"step8-{suffix}"
        self.now = at("2026-10-10T12:00:00Z")
        state, _page = save_new_entry(self.connection, self.url, 30, 5, 1, 100)
        self.assertEqual(state, "create")
        self.entry_id = self.connection.execute(
            "SELECT id FROM poll_entries WHERE url = %s",
            (self.url,),
        ).fetchone()["id"]
        created = create_group(self.connection, self.name)
        self.group_id = next(item["id"] for item in created["groups"] if item["name"] == self.name)
        save_email(self.connection, self.group_id, "ops@example.com")
        save_email(self.connection, self.group_id, "night@example.com")
        assign_group(self.connection, self.url, self.group_id, 1, 100)

    def tearDown(self):
        self.connection.rollback()
        self.connection.close()

    def test_status_follows_the_window_and_down_polls(self):
        future = self._window(self.now + timedelta(hours=1), self.now + timedelta(hours=2))
        self.assertEqual(future["status"], "NOT_STARTED")

        active = self._window(self.now - timedelta(minutes=30), self.now + timedelta(minutes=30))
        self.assertEqual(self._status(active["id"]), "STARTED_AND_UP")
        self._poll(self.now - timedelta(minutes=10), "Down detected")
        self.assertEqual(self._status(active["id"]), "STARTED_AND_DOWN")

        ended = self._window(self.now - timedelta(hours=2), self.now - timedelta(hours=1))
        self.assertEqual(ended["status"], "ENDED")

    def test_one_failure_does_not_send_mail(self):
        self._poll(self.now, "Down detected")
        reconcile_entry(self.connection, self.entry_id, self.now)
        self.assertEqual(self._mails(), [])

    def test_open_and_closed_incidents_mail_the_group(self):
        start = self.now
        self._poll(start, "Down detected")
        self._poll(start + timedelta(seconds=30), "Down detected")
        reconcile_entry(self.connection, self.entry_id, start + timedelta(seconds=30))
        mails = self._mails()
        self.assertEqual(len(mails), 1)
        self.assertEqual(mails[0]["addresses"], ["night@example.com", "ops@example.com"])
        self.assertEqual(
            mails[0]["message"],
            f"{self.url} downtime incident started at 2026-10-10 12:00:00 UTC.",
        )

        end = start + timedelta(seconds=60)
        self._poll(end, "OK", 200)
        reconcile_entry(self.connection, self.entry_id, end)
        messages = [row["message"] for row in self._mails()]
        self.assertIn(
            f"{self.url} downtime incident ended. "
            "It was started at 2026-10-10 12:00:00 UTC and ended at 2026-10-10 12:01:00 UTC.",
            messages,
        )
        reconcile_entry(self.connection, self.entry_id, end + timedelta(minutes=5))
        self.assertEqual(len(self._mails()), 2)

    def test_an_incident_inside_a_window_sends_nothing_even_after_delete(self):
        start = self.now
        self._window(start - timedelta(minutes=5), start + timedelta(hours=2))
        self._poll(start, "Down detected")
        self._poll(start + timedelta(seconds=30), "Down detected")
        self._poll(start + timedelta(seconds=60), "OK", 200)
        reconcile_entry(self.connection, self.entry_id, start + timedelta(minutes=30))
        self.assertEqual(self._mails(), [])

        maintenance_id = self._only_maintenance()
        delete_maintenance(self.connection, maintenance_id, 1, 10, 1, 10, start + timedelta(hours=3))
        reconcile_entry(self.connection, self.entry_id, start + timedelta(hours=3))
        self.assertEqual(self._mails(), [])

    def test_deleting_an_active_window_sends_the_open_incident(self):
        start = self.now
        window = self._window(start - timedelta(minutes=5), start + timedelta(hours=2))
        self._poll(start, "Down detected")
        self._poll(start + timedelta(seconds=30), "Down detected")
        moment = start + timedelta(minutes=10)
        reconcile_entry(self.connection, self.entry_id, moment)
        self.assertEqual(self._mails(), [])

        delete_maintenance(self.connection, window["id"], 1, 10, 1, 10, moment)
        mails = self._mails()
        self.assertEqual(len(mails), 1)
        self.assertIn("started at 2026-10-10 12:00:00 UTC", mails[0]["message"])

    def test_a_url_without_recipients_is_not_mailed(self):
        self.connection.execute(
            "DELETE FROM poll_group_emails WHERE poll_group_id = %s",
            (self.group_id,),
        )
        self._poll(self.now, "Down detected")
        self._poll(self.now + timedelta(seconds=30), "Down detected")
        reconcile_entry(self.connection, self.entry_id, self.now + timedelta(seconds=30))
        self.assertEqual(self._mails(), [])

    def test_a_group_window_suppresses_mail_for_its_urls(self):
        start = self.now
        create_maintenance(
            self.connection,
            "group",
            self.group_id,
            start - timedelta(minutes=5),
            start + timedelta(hours=1),
            1,
            10,
            1,
            10,
            self.now,
        )
        self._poll(start, "Down detected")
        self._poll(start + timedelta(seconds=30), "Down detected")
        reconcile_entry(self.connection, self.entry_id, start + timedelta(seconds=30))
        self.assertEqual(self._mails(), [])

    def test_old_closed_incidents_are_not_backfilled(self):
        start = self.now - timedelta(days=2)
        self._poll(start, "Down detected")
        self._poll(start + timedelta(seconds=30), "Down detected")
        self._poll(start + timedelta(seconds=60), "OK", 200)
        self._poll(start + timedelta(seconds=90), "OK", 200)
        reconcile_entry(self.connection, self.entry_id, self.now)
        self.assertEqual(self._mails(), [])

    def test_an_open_incident_is_mailed_after_a_restart(self):
        start = self.now - timedelta(days=1)
        self._poll(start, "Down detected")
        self._poll(start + timedelta(seconds=30), "Down detected")
        reconcile_entry(self.connection, self.entry_id, self.now)
        self.assertEqual(len(self._mails()), 1)
        self.assertIn("started at 2026-10-09 12:00:00 UTC", self._mails()[0]["message"])

    def test_end_must_be_after_the_start(self):
        with self.assertRaises(MaintenanceError):
            create_maintenance(
                self.connection,
                "url",
                self.entry_id,
                self.now,
                self.now,
                1,
                10,
                1,
                10,
                self.now,
            )

    def test_timestamp_must_be_utc_text(self):
        self.assertEqual(require_timestamp("2026-10-10T12:00:00Z", "Maintenance start"), self.now)
        with self.assertRaises(MaintenanceError):
            require_timestamp("tomorrow", "Maintenance start")

    def _window(self, starts_at: datetime, ends_at: datetime) -> dict:
        create_maintenance(
            self.connection,
            "url",
            self.entry_id,
            starts_at,
            ends_at,
            1,
            10,
            1,
            10,
            self.now,
        )
        row = self.connection.execute(
            """
            SELECT id, starts_at, ends_at
            FROM maintenances
            WHERE poll_entry_id = %s AND starts_at = %s AND ends_at = %s
            """,
            (self.entry_id, starts_at, ends_at),
        ).fetchone()
        self.assertIsNotNone(row)
        return {"id": row["id"], "status": self._status(row["id"])}

    def _status(self, maintenance_id: int) -> str:
        row = self.connection.execute(
            "SELECT starts_at, ends_at FROM maintenances WHERE id = %s",
            (maintenance_id,),
        ).fetchone()
        saw_down = self.connection.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM poll_history
                WHERE poll_entry_id = %s
                  AND message <> 'OK'
                  AND polled_at >= %s
                  AND polled_at < LEAST(%s, %s)
            ) AS saw_down
            """,
            (self.entry_id, row["starts_at"], row["ends_at"], self.now),
        ).fetchone()["saw_down"]
        return maintenance_status(row["starts_at"], row["ends_at"], saw_down, self.now)

    def _only_maintenance(self) -> int:
        rows = self.connection.execute(
            "SELECT id FROM maintenances WHERE poll_entry_id = %s",
            (self.entry_id,),
        ).fetchall()
        self.assertEqual(len(rows), 1)
        return rows[0]["id"]

    def _mails(self) -> list[dict]:
        return [row for row in list_mails(self.connection)["mails"] if self.url in row["message"]]

    def _poll(self, moment: datetime, message: str, http_status: int | None = 500) -> None:
        self.connection.execute(
            """
            INSERT INTO poll_history (poll_entry_id, polled_at, http_status, duration_ms, message)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (self.entry_id, moment, http_status, 10, message),
        )
