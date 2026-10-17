"""State machine and anti-false-alarm manager for server health status."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.checker import CheckResult

logger = logging.getLogger("cpanel_monitor.state")


class AlertAction(Enum):
    NONE = "none"
    TRIGGER_DOWN = "trigger_down"
    REMINDER_DOWN = "reminder_down"
    TRIGGER_RECOVERED = "trigger_recovered"


def format_duration(seconds: float) -> str:
    """Format duration in seconds into human-readable Indonesian string."""
    seconds = int(max(0, seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    parts: list[str] = []
    if hours > 0:
        parts.append(f"{hours} jam")
    if minutes > 0:
        parts.append(f"{minutes} menit")
    if secs > 0 or not parts:
        parts.append(f"{secs} detik")

    return " ".join(parts)


@dataclass
class TargetState:
    target: str
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    is_confirmed_down: bool = False
    downtime_start: datetime | None = None
    last_alert_time: datetime | None = None
    last_result: CheckResult | None = None
    total_checks: int = 0
    total_failures: int = 0

    def calculate_current_downtime_seconds(self) -> float:
        if not self.downtime_start:
            return 0.0
        return (datetime.now() - self.downtime_start).total_seconds()


class StateManager:
    """Tracks state across all monitored targets with anti-spam and recovery tracking."""

    def __init__(self) -> None:
        self.targets: dict[str, TargetState] = {}
        self.mute_until: datetime | None = None

    def get_or_create_state(self, target: str) -> TargetState:
        if target not in self.targets:
            self.targets[target] = TargetState(target=target)
        return self.targets[target]

    def remove_target(self, target: str) -> None:
        self.targets.pop(target, None)

    def mute(self, minutes: int) -> datetime:
        """Mute all alert notifications for a given number of minutes."""
        self.mute_until = datetime.now() + timedelta(minutes=minutes)
        return self.mute_until

    def unmute(self) -> None:
        """Unmute notifications immediately."""
        self.mute_until = None

    def is_muted(self) -> tuple[bool, str]:
        """Check if alerts are currently muted."""
        if self.mute_until is None:
            return False, ""
        now = datetime.now()
        if now < self.mute_until:
            remaining = (self.mute_until - now).total_seconds()
            return True, format_duration(remaining)
        # Mute expired
        self.mute_until = None
        return False, ""

    def process_result(
        self,
        result: CheckResult,
        threshold: int,
        reminder_minutes: int,
    ) -> tuple[AlertAction, TargetState, str]:
        """Update target state based on check result and return alert action needed.
        
        Returns:
            (AlertAction, TargetState, details_message)
        """
        state = self.get_or_create_state(result.target)
        state.last_result = result
        state.total_checks += 1
        now = datetime.now()

        # Check if muted
        muted, mute_time_left = self.is_muted()

        if result.is_up:
            state.consecutive_successes += 1
            state.consecutive_failures = 0

            # If it was confirmed down, trigger RECOVERED!
            if state.is_confirmed_down:
                downtime_duration = state.calculate_current_downtime_seconds()
                state.is_confirmed_down = False
                state.downtime_start = None
                state.last_alert_time = None
                duration_str = format_duration(downtime_duration)

                if muted:
                    logger.info("Target %s recovered, but notifications muted.", result.target)
                    return AlertAction.NONE, state, ""

                return AlertAction.TRIGGER_RECOVERED, state, duration_str

            return AlertAction.NONE, state, ""

        else:
            # Target is DOWN
            state.total_failures += 1
            state.consecutive_failures += 1
            state.consecutive_successes = 0

            # Start recording downtime on first failure if not already set
            if state.downtime_start is None:
                state.downtime_start = now

            if muted:
                # Still record state, but suppress alerts
                if state.consecutive_failures >= threshold:
                    state.is_confirmed_down = True
                return AlertAction.NONE, state, ""

            # Check if threshold reached
            if not state.is_confirmed_down:
                if state.consecutive_failures >= threshold:
                    state.is_confirmed_down = True
                    state.last_alert_time = now
                    details = f"Gagal {state.consecutive_failures} kali berturut-turut."
                    return AlertAction.TRIGGER_DOWN, state, details
                else:
                    # Still below threshold, wait for next checks to avoid false alarms
                    logger.warning(
                        "Target %s gagal (%d/%d): %s",
                        result.target,
                        state.consecutive_failures,
                        threshold,
                        result.error_message,
                    )
                    return AlertAction.NONE, state, ""

            else:
                # Already confirmed down, check for reminder interval
                if reminder_minutes > 0 and state.last_alert_time:
                    time_since_last_alert = (now - state.last_alert_time).total_seconds()
                    if time_since_last_alert >= (reminder_minutes * 60):
                        state.last_alert_time = now
                        current_downtime = format_duration(state.calculate_current_downtime_seconds())
                        return AlertAction.REMINDER_DOWN, state, current_downtime

                return AlertAction.NONE, state, ""
