import unittest

from xau_monitor.auth import (
    InvalidInput,
    hash_password,
    normalize_ip,
    normalize_username,
    token_hash,
    verify_password,
)


class PasswordTests(unittest.TestCase):
    def test_scrypt_hash_verifies_without_storing_plaintext(self) -> None:
        password = "correct horse battery staple"
        encoded = hash_password(password)

        self.assertNotIn(password, encoded)
        self.assertTrue(verify_password(password, encoded))
        self.assertFalse(verify_password("incorrect password value", encoded))

    def test_rejects_short_passwords(self) -> None:
        with self.assertRaises(InvalidInput):
            hash_password("too-short")


class IdentityTests(unittest.TestCase):
    def test_normalizes_username_for_unique_lookup(self) -> None:
        display, key = normalize_username("  Alice_01  ")
        self.assertEqual(display, "Alice_01")
        self.assertEqual(key, "alice_01")

    def test_accepts_single_character_usernames(self) -> None:
        self.assertEqual(normalize_username("j"), ("j", "j"))

    def test_rejects_ambiguous_username_characters(self) -> None:
        with self.assertRaises(InvalidInput):
            normalize_username("用户名字")

    def test_normalizes_ip_and_hashes_session_tokens(self) -> None:
        self.assertEqual(normalize_ip("2001:0db8::1"), "2001:db8::1")
        self.assertEqual(normalize_ip("not-an-ip"), "127.0.0.1")
        self.assertEqual(len(token_hash("session-token")), 64)


if __name__ == "__main__":
    unittest.main()
