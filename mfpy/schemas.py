"""Shared schemas for the mfpy backend."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TypedDict
from urllib.parse import urlparse


class BackupRecord(TypedDict):
    """Backup information for one modified file."""

    path: str
    existed: bool
    content: str


class LastChange(TypedDict):
    """Description of the last file change."""

    changed_at: str
    files: list[BackupRecord]


class HistoryData(TypedDict):
    """Persisted backend history."""

    version: int
    user_input: str
    selected_files: list[str]
    selected_behaviors: list[str]
    save_output: bool
    last_result: str
    last_change: LastChange


@dataclass(frozen=True)
class MfConfig:
    """LLM endpoint configuration."""

    url: str
    api_key: str
    model: str
    timeout_seconds: int = 120
    max_attempts: int = 4
    backoff_base: float = 1.0

    @classmethod
    def from_environment(cls) -> "MfConfig":
        """Create configuration from environment variables."""
        return cls(
            url=os.environ.get("MFPLUGIN_URL", ""),
            api_key=os.environ.get("MFPLUGIN_API_KEY", ""),
            model=os.environ.get("MFPLUGIN_MODEL", ""),
        )

    def validate(self) -> None:
        """Validate required endpoint settings.

        Raises:
            ValueError: If a setting is missing or the URL is invalid.
        """
        if not self.url.strip():
            raise ValueError(
                "The LLM URL is missing. Set MFPLUGIN_URL or pass --url."
            )
        if not self.api_key.strip():
            raise ValueError(
                "The API key is missing. Set MFPLUGIN_API_KEY or pass "
                "--api-key."
            )
        if not self.model.strip():
            raise ValueError(
                "The model is missing. Set MFPLUGIN_MODEL or pass --model."
            )

        parsed = urlparse(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("The LLM URL must be a valid HTTP or HTTPS URL.")

        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be greater than zero.")
        if self.backoff_base < 0:
            raise ValueError("backoff_base cannot be negative.")