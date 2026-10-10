import unittest

import json
from pathlib import Path

from backend.entries import (
    EntryError,
    clamp_page,
    creation_action,
    health_fields,
    require_page_size,
    require_saved_url,
    require_seconds,
    require_url,
    status_event,
)


class CreationTests(unittest.TestCase):
    def test_missing_url_is_created(self):
        self.assertEqual(creation_action(None), "create")

    def test_deleted_url_is_restored(self):
        self.assertEqual(creation_action("DELETED"), "restore")

    def test_live_url_already_exists(self):
        self.assertEqual(creation_action("ACTIVE"), "exists")
        self.assertEqual(creation_action("PAUSED"), "exists")


class HealthTests(unittest.TestCase):
    def test_no_history_is_blank(self):
        self.assertEqual(health_fields(None), ("", ""))

    def test_ok_is_up_without_an_error(self):
        self.assertEqual(health_fields("OK"), ("UP", ""))

    def test_any_other_message_is_down(self):
        self.assertEqual(health_fields("Down detected"), ("DOWN", "Down detected"))
        self.assertEqual(health_fields("404"), ("DOWN", "404"))


class PageTests(unittest.TestCase):
    def test_page_past_the_end_moves_to_the_last_page(self):
        self.assertEqual(clamp_page(9, 10, 15), 2)
        self.assertEqual(clamp_page(1, 10, 0), 1)

    def test_page_size_must_be_one_of_the_listed_values(self):
        self.assertEqual(require_page_size(25), 25)
        with self.assertRaises(EntryError):
            require_page_size(15)

    def test_seconds_and_url_are_checked(self):
        self.assertEqual(require_seconds(30, "Polling rate"), 30)
        with self.assertRaises(EntryError):
            require_seconds(True, "Polling rate")
        with self.assertRaises(EntryError):
            require_url("   ")
        self.assertEqual(require_url("  https://www.google.com  "), "https://www.google.com")
        self.assertEqual(require_url("http://google.com/"), "http://google.com")
        self.assertEqual(require_url("http://google.com/page/"), "http://google.com/page/")
        self.assertEqual(require_url("HTTP://Google.com/Foo"), "http://google.com/Foo")
        self.assertEqual(require_url("www.google.com"), "http://www.google.com")
        self.assertEqual(require_url("localhost:8080/health"), "http://localhost:8080/health")
        self.assertEqual(require_url("https://example.com:443/a"), "https://example.com:443/a")
        with self.assertRaises(EntryError):
            require_url("google.com")
        self.assertEqual(require_saved_url("  anime.com  "), "anime.com")
        self.assertEqual(require_saved_url("https://www.anime.com/"), "https://www.anime.com/")
        with self.assertRaises(EntryError):
            require_url("ftp://google.com")

    def test_seed_urls_are_accepted(self):
        payload = json.loads(Path("init-poll-entries.json").read_text(encoding="utf-8"))
        normalized = [require_url(item["url"]) for item in payload]
        self.assertEqual(normalized[0], "https://www.google.com")
        self.assertFalse(normalized[1].endswith("/"))
        self.assertEqual(normalized[2], "http://localhost:17777")

    def test_status_changes_that_are_logged(self):
        self.assertEqual(status_event("ACTIVE", "PAUSED"), "paused")
        self.assertEqual(status_event("PAUSED", "ACTIVE"), "resumed")
        self.assertIsNone(status_event("ACTIVE", "ACTIVE"))
        self.assertIsNone(status_event("PAUSED", "PAUSED"))
