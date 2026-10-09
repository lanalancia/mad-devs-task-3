import unittest

from backend.entries import (
    EntryError,
    clamp_page,
    creation_action,
    health_fields,
    require_page_size,
    require_seconds,
    require_url,
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
