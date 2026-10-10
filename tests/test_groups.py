import unittest

from backend.groups import (
    GroupError,
    group_health,
    poll_state,
    require_email,
    require_group_name,
    response_status,
    should_poll,
)


class ResponseStatusTests(unittest.TestCase):
    def test_empty_group_stays_empty_when_the_group_is_paused(self):
        self.assertEqual(response_status(True, []), "EMPTY")
        self.assertEqual(response_status(False, []), "EMPTY")

    def test_every_url_paused_wins_over_the_group_pause(self):
        members = [("PAUSED", "OK"), ("PAUSED", None)]
        self.assertEqual(response_status(True, members), "URLS_PAUSED")
        self.assertEqual(response_status(False, members), "URLS_PAUSED")

    def test_group_pause_applies_when_a_url_is_still_active(self):
        members = [("ACTIVE", "OK"), ("PAUSED", "Down detected")]
        self.assertEqual(response_status(True, members), "GROUP_PAUSED")

    def test_polling_is_the_remaining_case(self):
        members = [("ACTIVE", "OK"), ("PAUSED", None)]
        self.assertEqual(response_status(False, members), "POLLING")


class GroupHealthTests(unittest.TestCase):
    def test_health_is_withheld_unless_the_group_is_polling(self):
        members = [("ACTIVE", "OK")]
        self.assertEqual(group_health("EMPTY", []), "NO_DATA_YET")
        self.assertEqual(group_health("URLS_PAUSED", [("PAUSED", "OK")]), "NO_DATA_YET")
        self.assertEqual(group_health("GROUP_PAUSED", members), "NO_DATA_YET")

    def test_down_wins_when_one_active_url_is_down(self):
        members = [("ACTIVE", "OK"), ("ACTIVE", "Down detected"), ("PAUSED", "Down detected")]
        self.assertEqual(group_health("POLLING", members), "DOWN")

    def test_up_ignores_paused_urls(self):
        members = [("ACTIVE", "OK"), ("PAUSED", None), ("PAUSED", "404")]
        self.assertEqual(group_health("POLLING", members), "UP")

    def test_missing_history_on_an_active_url_is_not_up(self):
        members = [("ACTIVE", "OK"), ("ACTIVE", None)]
        self.assertEqual(group_health("POLLING", members), "NO_DATA_YET")

    def test_paused_url_without_history_does_not_block_up(self):
        members = [("ACTIVE", "OK"), ("PAUSED", None)]
        self.assertEqual(group_health("POLLING", members), "UP")


class PollStateTests(unittest.TestCase):
    def test_the_url_pause_wins_over_the_group_pause(self):
        self.assertEqual(poll_state("PAUSED", True), "URL_PAUSED")
        self.assertEqual(poll_state("PAUSED", None), "URL_PAUSED")

    def test_group_pause_shows_only_while_the_url_is_active(self):
        self.assertEqual(poll_state("ACTIVE", True), "GROUP_PAUSED")
        self.assertEqual(poll_state("ACTIVE", False), "ACTIVE")
        self.assertEqual(poll_state("ACTIVE", None), "ACTIVE")

    def test_polling_requires_both_switches_to_be_open(self):
        self.assertTrue(should_poll("ACTIVE", None))
        self.assertTrue(should_poll("ACTIVE", False))
        self.assertFalse(should_poll("ACTIVE", True))
        self.assertFalse(should_poll("PAUSED", False))
        self.assertFalse(should_poll("PAUSED", None))


class NameAndEmailTests(unittest.TestCase):
    def test_name_rules(self):
        self.assertEqual(require_group_name("  api  "), "api")
        with self.assertRaises(GroupError):
            require_group_name("   ")
        with self.assertRaises(GroupError):
            require_group_name("x" * 51)

    def test_email_rules(self):
        self.assertEqual(require_email("  ops@example.com  "), "ops@example.com")
        with self.assertRaises(GroupError):
            require_email("   ")
        with self.assertRaises(GroupError):
            require_email("not-an-email")
