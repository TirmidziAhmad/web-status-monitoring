"""Unit tests for StateManager, anti-false-alarm, and alert transitions."""

from datetime import datetime, timedelta
import unittest

from src.checker import CheckResult
from src.state import AlertAction, StateManager, format_duration


class TestStateManager(unittest.TestCase):
    def setUp(self):
        self.state_mgr = StateManager()
        self.target = "https://example.com"
        self.threshold = 3
        self.reminder_minutes = 30

    def make_result(self, is_up: bool, status_code: int = 200, error: str = None) -> CheckResult:
        return CheckResult(
            target=self.target,
            is_up=is_up,
            status_code=status_code,
            latency_ms=50.0,
            error_message=error,
            checked_at=datetime.now(),
        )

    def test_single_failure_does_not_trigger_alert(self):
        # 1st fail: below threshold (1/3)
        action, state, _ = self.state_mgr.process_result(
            self.make_result(False, 502, "Bad Gateway"),
            self.threshold,
            self.reminder_minutes,
        )
        self.assertEqual(action, AlertAction.NONE)
        self.assertEqual(state.consecutive_failures, 1)
        self.assertFalse(state.is_confirmed_down)

        # 2nd fail: still below threshold (2/3)
        action, state, _ = self.state_mgr.process_result(
            self.make_result(False, 502, "Bad Gateway"),
            self.threshold,
            self.reminder_minutes,
        )
        self.assertEqual(action, AlertAction.NONE)
        self.assertEqual(state.consecutive_failures, 2)
        self.assertFalse(state.is_confirmed_down)

    def test_reaches_threshold_triggers_down_alert(self):
        # Fail 1 & 2
        self.state_mgr.process_result(self.make_result(False, 502), self.threshold, self.reminder_minutes)
        self.state_mgr.process_result(self.make_result(False, 502), self.threshold, self.reminder_minutes)

        # 3rd fail: reaches threshold!
        action, state, details = self.state_mgr.process_result(
            self.make_result(False, 502, "Bad Gateway"),
            self.threshold,
            self.reminder_minutes,
        )
        self.assertEqual(action, AlertAction.TRIGGER_DOWN)
        self.assertTrue(state.is_confirmed_down)
        self.assertIn("Gagal 3 kali", details)

    def test_continuous_failure_and_recovery(self):
        # Trigger DOWN
        for _ in range(self.threshold):
            self.state_mgr.process_result(self.make_result(False, 502), self.threshold, self.reminder_minutes)

        state = self.state_mgr.get_or_create_state(self.target)
        self.assertTrue(state.is_confirmed_down)

        # Simulate 15 minutes of downtime passed
        state.downtime_start = datetime.now() - timedelta(minutes=15, seconds=30)

        # Now server comes back UP!
        action, state, duration_str = self.state_mgr.process_result(
            self.make_result(True, 200),
            self.threshold,
            self.reminder_minutes,
        )
        self.assertEqual(action, AlertAction.TRIGGER_RECOVERED)
        self.assertFalse(state.is_confirmed_down)
        self.assertIn("15 menit", duration_str)

    def test_mute_suppresses_alerts(self):
        self.state_mgr.mute(minutes=30)
        is_muted, _ = self.state_mgr.is_muted()
        self.assertTrue(is_muted)

        # Even if threshold is reached while muted, no alert should be dispatched
        for _ in range(self.threshold):
            action, _, _ = self.state_mgr.process_result(
                self.make_result(False, 502),
                self.threshold,
                self.reminder_minutes,
            )
            self.assertEqual(action, AlertAction.NONE)

        # Unmute
        self.state_mgr.unmute()
        is_muted, _ = self.state_mgr.is_muted()
        self.assertFalse(is_muted)

    def test_format_duration(self):
        self.assertEqual(format_duration(45), "45 detik")
        self.assertEqual(format_duration(125), "2 menit 5 detik")
        self.assertEqual(format_duration(3665), "1 jam 1 menit 5 detik")


if __name__ == "__main__":
    unittest.main()
