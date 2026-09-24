"""Top-level backend workflow orchestration service."""

from __future__ import annotations

import time
from collections.abc import Iterable

from mfpy.services.file_change_service import FileChangeService
from mfpy.services.history_service import HistoryService
from mfpy.services.llm_service import LlmService
from mfpy.services.prompt_service import PromptService


class WorkflowService:
    """Coordinate history, prompt, LLM, and file change services."""

    def __init__(
        self,
        history: HistoryService,
        prompt: PromptService,
        llm: LlmService,
        file_changes: FileChangeService,
    ) -> None:
        """Initialize workflow dependencies."""
        self.history = history
        self.prompt = prompt
        self.llm = llm
        self.file_changes = file_changes

    def build_result(
        self,
        selected_files: list[str],
        user_input: str,
        save_output: bool,
        selected_behaviors: Iterable[str] | None = None,
    ) -> str:
        """Run one complete user request."""
        normalized_files = self.history.normalize_string_list(selected_files)
        normalized_behaviors = self.history.normalize_behavior_names(
            list(selected_behaviors or [])
        )
        save_output = bool(save_output)
        user_input = str(user_input)

        history = self.history.load()
        history.update(
            {
                "user_input": user_input,
                "selected_files": normalized_files,
                "selected_behaviors": normalized_behaviors,
                "save_output": save_output,
            }
        )
        self.history.write(history)

        prompt = self.prompt.build(
            normalized_files,
            user_input,
            save_output,
            normalized_behaviors,
        )
        response = self.llm.send(prompt)

        if not save_output:
            return self._persist_result(response)

        mapping = self.file_changes.extract_files(response)
        if not mapping:
            return self._persist_result(
                "No file blocks found in the response. "
                "No files were updated."
            )

        backups, files_to_write, skipped = (
            self.file_changes.collect_backups(mapping)
        )
        if files_to_write:
            history = self.history.load()
            history.update(
                {
                    "user_input": user_input,
                    "selected_files": normalized_files,
                    "selected_behaviors": normalized_behaviors,
                    "save_output": save_output,
                    "last_change": {
                        "changed_at": time.strftime(
                            "%Y-%m-%dT%H:%M:%S%z"
                        ),
                        "files": backups,
                    },
                }
            )
            self.history.write(history)
            self.file_changes.write_files(files_to_write)

        result = self._format_write_result(files_to_write, skipped)
        return self._persist_result(result)

    def _persist_result(self, result: str) -> str:
        """Persist the latest popup content and return it unchanged."""
        history = self.history.load()
        history["last_result"] = result
        self.history.write(history)
        return result

    @staticmethod
    def _format_write_result(
        files_to_write: list[tuple],
        skipped: list[str],
    ) -> str:
        lines: list[str] = []
        if files_to_write:
            lines.append("Files updated:")
            lines.extend(item[2] for item in files_to_write)
            lines.extend(
                [
                    "End of updated files",
                    "",
                    "Original content was stored in .mfhist. "
                    "Use Revert last change to restore it.",
                ]
            )
        else:
            lines.append("No files were updated.")

        if skipped:
            lines.extend(["", "Skipped files:", *skipped])

        return "\n".join(lines)