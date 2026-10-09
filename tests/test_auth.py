import unittest

from backend.auth import issue_token, passwords_match, read_token


class PasswordTests(unittest.TestCase):
    def test_same_password_matches(self):
        self.assertTrue(passwords_match("admin", "admin"))

    def test_different_password_does_not_match(self):
        self.assertFalse(passwords_match("admin", "other"))


class TokenTests(unittest.TestCase):
    def test_token_is_valid_until_the_hour_is_up(self):
        token = issue_token("admin", "secret", now=1_000)
        self.assertEqual(read_token(token, "secret", now=1_000), ("ok", "admin"))
        self.assertEqual(read_token(token, "secret", now=4_599), ("ok", "admin"))
        self.assertEqual(read_token(token, "secret", now=4_600), ("expired", ""))

    def test_wrong_secret_is_invalid(self):
        token = issue_token("admin", "secret", now=1_000)
        self.assertEqual(read_token(token, "other", now=1_000), ("invalid", ""))

    def test_tampered_token_is_invalid(self):
        token = issue_token("admin", "secret", now=1_000)
        self.assertEqual(read_token(token + "x", "secret", now=1_000), ("invalid", ""))
        self.assertEqual(read_token("not-a-token", "secret", now=1_000), ("invalid", ""))
