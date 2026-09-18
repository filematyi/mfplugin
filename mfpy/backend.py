"""Public backend facade.

Functionality lives in dedicated services. This class keeps the existing
backend API stable for callers.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from mfpy.behaviors.collection import (
    behaviors as REGISTERED_BEHAVIORS,
)
from mfpy.schemas import MfConfig
from mfpy.services.file_change_service import (
    FILE_BLOCK_PATTERN,
    FileChangeService,
)
from mfpy.services.filesystem_service import (
    DEFAULT_FILE_PATH_BLACKLIST_SUBSTRINGS,
    FileSystemService,
)
from mfpy.services.history_service import HistoryService
from mfpy.services.llm_service import LlmService
from mfpy.services.prompt_service import PromptService
from mfpy.services.workflow_service import WorkflowService


class MfBackend:
    """Facade for project context, LLM calls, and generated file changes."""

    def __init__(
        self,
        root_path: str | os.PathLike[str],
        config: MfConfig,
        blacklist_substrings: Iterable[str] | None = None,
    ) -> None:
        """Initialize backend services."""
        self._config = config
        self.filesystem_service = FileSystemService(
            root_path,
            blacklist_substrings,
        )
        self.root = self.filesystem_service.root
        self.blacklist_substrings = (
            self.filesystem_service.blacklist_substrings
        )

        self.history_service = HistoryService(
            self.root,
            REGISTERED_BEHAVIORS,
        )
        self.prompt_service = PromptService(
            self.filesystem_service,
            self.history_service,
            REGISTERED_BEHAVIORS,
        )
        self.llm_service = LlmService(config)
        self.file_change_service = FileChangeService(
            self.filesystem_service,
            self.history_service,
        )
        self.workflow_service = WorkflowService(
            self.history_service,
            self.prompt_service,
            self.llm_service,
            self.file_change_service,
        )

    @property
    def config(self) -> MfConfig:
        """Return the active LLM configuration."""
        return self._config

    @config.setter
    def config(self, config: MfConfig) -> None:
        """Update configuration used by subsequent LLM requests."""
        self._config = config
        self.llm_service.config = config

    @property
    def history_path(self) -> Path:
        """Return the .mfhist path."""
        return self.history_service.path

    @staticmethod
    def default_history() -> dict:
        """Return default history data."""
        return HistoryService.default_history()

    @staticmethod
    def normalize_string_list(value) -> list[str]:
        """Normalize a list of strings."""
        return HistoryService.normalize_string_list(value)

    @classmethod
    def normalize_behavior_names(cls, value) -> list[str]:
        """Normalize registered behavior names."""
        service = HistoryService(Path.cwd(), REGISTERED_BEHAVIORS)
        return service.normalize_behavior_names(value)

    def load_history(self) -> dict:
        """Load persisted history."""
        return self.history_service.load()

    def write_history(self, history: dict) -> None:
        """Persist history atomically."""
        self.history_service.write(history)

    def is_blacklisted(self, path: str | os.PathLike[str]) -> bool:
        """Return whether a path is blacklisted."""
        return self.filesystem_service.is_blacklisted(path)

    def list_entries(self) -> list[str]:
        """List selectable project entries."""
        return self.filesystem_service.list_entries(self.history_path)

    def resolve_inside_root(self, path: str) -> Path:
        """Resolve a root-confined path."""
        return self.filesystem_service.resolve_inside_root(path)

    def relative_path(self, path: Path) -> str:
        """Return a project-relative path."""
        return self.filesystem_service.relative_path(path)

    def read_file(self, path: Path) -> str:
        """Read a text file."""
        return self.filesystem_service.read_file(path)

    @staticmethod
    def save_file(path: Path, content: str) -> None:
        """Save a text file."""
        FileSystemService.save_file(path, content)

    def resolve_selected_files(
        self,
        selected_paths: Iterable[str],
    ) -> list[Path]:
        """Expand selected paths into files."""
        return self.filesystem_service.resolve_selected_files(
            selected_paths,
            self.history_path,
        )

    def build_prompt(
        self,
        selected_files: list[str],
        user_input: str,
        save_output: bool,
        selected_behaviors: Iterable[str] | None = None,
    ) -> str:
        """Build an LLM prompt."""
        return self.prompt_service.build(
            selected_files,
            user_input,
            save_output,
            selected_behaviors,
        )

    def send_llm_call(self, prompt: str) -> str:
        """Send a prompt to the configured LLM."""
        return self.llm_service.send(prompt)

    @staticmethod
    def extract_files(text: str) -> dict[str, str]:
        """Extract generated file blocks."""
        return FileChangeService.extract_files(text)

    def collect_backups_for_mapping(
        self,
        mapping: dict[str, str],
    ) -> tuple[list[dict], list[tuple[Path, str, str]], list[str]]:
        """Prepare generated files and backups."""
        return self.file_change_service.collect_backups(mapping)

    def build_result(
        self,
        selected_files: list[str],
        user_input: str,
        save_output: bool,
        selected_behaviors: Iterable[str] | None = None,
    ) -> str:
        """Run the complete backend workflow."""
        return self.workflow_service.build_result(
            selected_files,
            user_input,
            save_output,
            selected_behaviors,
        )

    def revert_last_change(self) -> str:
        """Revert the most recent generated file change."""
        return self.file_change_service.revert_last_change()