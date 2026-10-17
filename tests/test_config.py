"""Unit tests for ConfigManager and dynamic persistence."""

import json
from pathlib import Path
import tempfile
import unittest

from src.config import ConfigManager, normalize_target_url


class TestConfigManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.env_file = self.base_dir / ".env"
        self.env_file.write_text(
            "TELEGRAM_BOT_TOKEN=test_token_123\n"
            "TELEGRAM_CHAT_ID=111,222\n"
            "TARGET_URLS=https://example.com,http://test.local:2083\n"
            "CHECK_INTERVAL_SECONDS=45\n"
            "FAILURE_THRESHOLD=2\n"
            "REMINDER_INTERVAL_MINUTES=15\n"
            "DATA_DIR=data\n"
        )
        self.config = ConfigManager(env_path=self.env_file, base_dir=self.base_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_initial_values_loaded(self):
        self.assertEqual(self.config.bot_token, "test_token_123")
        self.assertEqual(self.config.admin_chat_ids, [111, 222])
        self.assertEqual(self.config.get_targets(), ["https://example.com", "http://test.local:2083"])
        self.assertEqual(self.config.check_interval_seconds, 45)
        self.assertEqual(self.config.failure_threshold, 2)
        self.assertEqual(self.config.reminder_interval_minutes, 15)

    def test_normalize_target_url(self):
        self.assertEqual(normalize_target_url("prima.rsmra.id"), "https://prima.rsmra.id")
        self.assertEqual(normalize_target_url("http://domain.com/"), "http://domain.com")
        self.assertEqual(normalize_target_url("https://domain.com:2083/cpanel"), "https://domain.com:2083/cpanel")
        self.assertEqual(normalize_target_url("   "), "")

    def test_dynamic_add_target(self):
        success, msg = self.config.add_target("sub.domain.com:2083")
        self.assertTrue(success)
        self.assertIn("https://sub.domain.com:2083", self.config.get_targets())

        # Adding duplicate should fail gracefully
        success_dup, msg_dup = self.config.add_target("sub.domain.com:2083")
        self.assertFalse(success_dup)

    def test_dynamic_remove_target(self):
        success, msg = self.config.remove_target("https://example.com")
        self.assertTrue(success)
        self.assertNotIn("https://example.com", self.config.get_targets())

        # Removing non-existing should fail
        fail_res, _ = self.config.remove_target("https://nonexistent.org")
        self.assertFalse(fail_res)

    def test_dynamic_interval_and_threshold(self):
        # Valid interval
        succ, _ = self.config.set_interval(30)
        self.assertTrue(succ)
        self.assertEqual(self.config.check_interval_seconds, 30)

        # Invalid intervals
        fail_low, _ = self.config.set_interval(2)
        self.assertFalse(fail_low)

        # Threshold
        succ_t, _ = self.config.set_threshold(4)
        self.assertTrue(succ_t)
        self.assertEqual(self.config.failure_threshold, 4)

    def test_persistence_across_reloads(self):
        self.config.add_target("https://persisted-domain.com")
        self.config.set_interval(90)
        self.config.set_threshold(5)

        # Create new ConfigManager pointing to same directory
        reloaded_config = ConfigManager(env_path=self.env_file, base_dir=self.base_dir)
        self.assertIn("https://persisted-domain.com", reloaded_config.get_targets())
        self.assertEqual(reloaded_config.check_interval_seconds, 90)
        self.assertEqual(reloaded_config.failure_threshold, 5)

    def test_auth_check(self):
        self.assertTrue(self.config.is_authorized(111))
        self.assertTrue(self.config.is_authorized("222"))
        self.assertFalse(self.config.is_authorized(999))


if __name__ == "__main__":
    unittest.main()
