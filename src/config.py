"""Configuration and dynamic runtime settings manager for cPanel Monitor Bot."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

logger = logging.getLogger("cpanel_monitor.config")


def normalize_target_url(url: str) -> str:
    """Normalize input target URL to ensure scheme is present and clean whitespace."""
    url = url.strip()
    if not url:
        return ""
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.netloc:
        return ""
    # Remove trailing slash if path is empty or root
    normalized = f"{parsed.scheme}://{parsed.netloc}"
    if parsed.path and parsed.path != "/":
        normalized += parsed.path
    if parsed.query:
        normalized += f"?{parsed.query}"
    return normalized


class ConfigManager:
    """Manages static environment variables and dynamic runtime configurations."""

    def __init__(self, env_path: Path | str | None = None, base_dir: Path | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).resolve().parent.parent
        self.env_path = Path(env_path) if env_path else (self.base_dir / ".env")

        # Load environment variables if file exists
        if self.env_path.exists():
            load_dotenv(self.env_path)

        self.bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        raw_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.admin_chat_ids: list[int] = self._parse_chat_ids(raw_chat_id)

        data_dir_env = os.getenv("DATA_DIR", "data").strip()
        self.data_dir = (self.base_dir / data_dir_env).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_config_file = self.data_dir / "config.json"

        # Defaults from .env
        raw_targets = os.getenv("TARGET_URLS", "https://prima.rsmra.id").strip()
        default_targets: list[str] = []
        for item in raw_targets.split(","):
            cleaned = normalize_target_url(item)
            if cleaned and cleaned not in default_targets:
                default_targets.append(cleaned)

        self.default_interval = int(os.getenv("CHECK_INTERVAL_SECONDS", "60"))
        self.default_threshold = int(os.getenv("FAILURE_THRESHOLD", "3"))
        self.reminder_interval_minutes = int(os.getenv("REMINDER_INTERVAL_MINUTES", "30"))
        self.request_timeout_seconds = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "10"))

        # In-memory dynamic settings
        self.target_urls: list[str] = list(default_targets)
        self.check_interval_seconds: int = self.default_interval
        self.failure_threshold: int = self.default_threshold

        # Load persisted runtime config if exists
        self._load_runtime_config()

    def _parse_chat_ids(self, raw_str: str) -> list[int]:
        ids: list[int] = []
        for part in raw_str.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                ids.append(int(part))
            except ValueError:
                logger.warning("Invalid chat ID in configuration: %s", part)
        return ids

    def _load_runtime_config(self) -> None:
        """Load overrides from runtime config.json if present."""
        if not self.runtime_config_file.exists():
            # Save initial defaults
            self._save_runtime_config()
            return

        try:
            with open(self.runtime_config_file, "r", encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)

            if "target_urls" in data and isinstance(data["target_urls"], list):
                loaded_targets: list[str] = []
                for t in data["target_urls"]:
                    norm = normalize_target_url(str(t))
                    if norm and norm not in loaded_targets:
                        loaded_targets.append(norm)
                if loaded_targets:
                    self.target_urls = loaded_targets

            if "check_interval_seconds" in data:
                val = int(data["check_interval_seconds"])
                if val >= 5:
                    self.check_interval_seconds = val

            if "failure_threshold" in data:
                val = int(data["failure_threshold"])
                if val >= 1:
                    self.failure_threshold = val

            if "reminder_interval_minutes" in data:
                self.reminder_interval_minutes = max(0, int(data["reminder_interval_minutes"]))

        except Exception as e:
            logger.error("Failed to load %s: %s. Using default settings.", self.runtime_config_file, e)

    def _save_runtime_config(self) -> None:
        """Save current dynamic configuration to config.json atomically."""
        try:
            data = {
                "target_urls": self.target_urls,
                "check_interval_seconds": self.check_interval_seconds,
                "failure_threshold": self.failure_threshold,
                "reminder_interval_minutes": self.reminder_interval_minutes,
            }
            temp_file = self.runtime_config_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            temp_file.replace(self.runtime_config_file)
            logger.info("Runtime configuration saved successfully to %s", self.runtime_config_file)
        except Exception as e:
            logger.error("Error saving runtime configuration to %s: %s", self.runtime_config_file, e)

    def get_targets(self) -> list[str]:
        return list(self.target_urls)

    def add_target(self, url: str) -> tuple[bool, str]:
        """Add a target URL dynamically. Returns (success, normalized_url_or_error)."""
        normalized = normalize_target_url(url)
        if not normalized:
            return False, "URL target tidak valid. Contoh format: https://domainanda.com atau https://domainanda.com:2083"
        if normalized in self.target_urls:
            return False, f"URL '{normalized}' sudah ada dalam daftar pemantauan."

        self.target_urls.append(normalized)
        self._save_runtime_config()
        return True, normalized

    def remove_target(self, url: str) -> tuple[bool, str]:
        """Remove a target URL dynamically. Returns (success, message)."""
        normalized = normalize_target_url(url)
        # Search direct match or normalized match
        match = None
        for t in self.target_urls:
            if t.lower() == normalized.lower() or t.lower() == url.strip().lower():
                match = t
                break

        if not match:
            return False, f"URL '{url}' tidak ditemukan dalam daftar pemantauan."

        self.target_urls.remove(match)
        self._save_runtime_config()
        return True, match

    def set_interval(self, seconds: int) -> tuple[bool, str]:
        """Set check interval dynamically in seconds. Minimum 5 seconds."""
        if seconds < 5:
            return False, "Interval pengecekan minimal 5 detik untuk menghindari beban berlebih."
        if seconds > 86400:
            return False, "Interval pengecekan maksimal 86400 detik (24 jam)."

        self.check_interval_seconds = seconds
        self._save_runtime_config()
        return True, f"Interval pengecekan berhasil diubah menjadi {seconds} detik."

    def set_threshold(self, threshold: int) -> tuple[bool, str]:
        """Set failure threshold dynamically."""
        if threshold < 1:
            return False, "Threshold minimal 1 kali."
        if threshold > 20:
            return False, "Threshold maksimal 20 kali."

        self.failure_threshold = threshold
        self._save_runtime_config()
        return True, f"Threshold kegagalan berhasil diubah menjadi {threshold} kali."

    def is_authorized(self, chat_id: int | str) -> bool:
        """Check if chat_id is authorized as admin. If no admins configured, allow anyone for initial setup."""
        if not self.admin_chat_ids:
            return True
        try:
            return int(chat_id) in self.admin_chat_ids
        except (ValueError, TypeError):
            return False

    def add_admin_chat_id(self, chat_id: int) -> None:
        """Automatically register chat ID if none configured yet."""
        if chat_id not in self.admin_chat_ids:
            self.admin_chat_ids.append(chat_id)
            logger.info("Admin Chat ID %s registered.", chat_id)
