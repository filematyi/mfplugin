"""History persistence and normalization service."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Collection

from ..schemas import HistoryData


class HistoryService:
    """Manage the project-local .mfhist file."""

    def __init__(
        self,
        root: Path,
        registered_behaviors: Collection[str],
    ) -> None:
        """Initialize the service.

        Args:
            root: Selected project root.
            registered_behaviors: Names of available behaviors.
        """
        self.root = root
        self.registered_behaviors = set(registered_behaviors)

    @property
    def path(self) -> Path:
        """Return the history file path."""
        return self.root / ".mfhist"

    @staticmethod
    def default_history() -> HistoryData:
        """Return an empty normalized history."""
        return {
            "version": 3,
            "user_input": "",
            "selected_files": [],
            "selected_behaviors": [],
            "save_output": False,
            "last_change": {
                "changed_at": "",
                "files": [],
            },
        }

    @staticmethod
    def normalize_string_list(value: Any) -> list[str]:
        """Normalize a value into unique, non-empty strings."""
        if not isinstance(value, list):
            return []

        result: list[str] = []
        seen: set[str] = set()

        for item in value:
            text = str(item).strip()
            if text and text not in seen:
                seen.add(text)
                result.append(text)

        return result

    def normalize_behavior_names(self, value: Any) -> list[str]:
        """Return valid, unique behavior names."""
        return [
            name
            for name in self.normalize_string_list(value)
            if name in self.registered_behaviors
        ]

    def normalize_history(self, value: Any) -> HistoryData:
        """Normalize untrusted history data."""
        history = self.default_history()
        if not isinstance(value, dict):
            history["user_input"] = str(value)
            return history

        user_input = value.get("user_input", "")
        history["user_input"] = (
            user_input if isinstance(user_input, str) else str(user_input)
        )
        history["selected_files"] = self.normalize_string_list(
            value.get("selected_files", [])
        )
        history["selected_behaviors"] = self.normalize_behavior_names(
            value.get("selected_behaviors", [])
        )
        history["save_output"] = bool(value.get("save_output", False))

        last_change = value.get("last_change", {})
        if isinstance(last_change, dict):
            changed_at = last_change.get("changed_at", "")
            files = last_change.get("files", [])
            history["last_change"] = {
                "changed_at": (
                    changed_at
                    if isinstance(changed_at, str)
                    else str(changed_at)
                ),
                "files": files if isinstance(files, list) else [],
            }

        return history

    def load(self) -> HistoryData:
        """Load history, falling back to defaults for invalid content."""
        if not self.path.is_file():
            return self.default_history()

        raw = self.path.read_text(encoding="utf-8")
        if not raw:
            return self.default_history()

        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            history = self.default_history()
            history["user_input"] = raw
            return history

        return self.normalize_history(parsed)

    def write(self, history: dict[str, Any]) -> None:
        """Atomically persist normalized history."""
        data = self.normalize_history(history)
        self.root.mkdir(parents=True, exist_ok=True)

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".mfhist.",
            suffix=".tmp",
            dir=self.root,
            text=True,
        )

        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            os.replace(temporary_name, self.path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)