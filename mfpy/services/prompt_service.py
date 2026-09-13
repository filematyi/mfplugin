"""LLM prompt construction service."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .filesystem_service import FileSystemService
from .history_service import HistoryService


class PromptService:
    """Build prompts from user input, behaviors, and selected files."""

    def __init__(
        self,
        filesystem: FileSystemService,
        history: HistoryService,
        behaviors: Mapping[str, str],
    ) -> None:
        """Initialize the service dependencies."""
        self.filesystem = filesystem
        self.history = history
        self.behaviors = behaviors

    def build(
        self,
        selected_files: list[str],
        user_input: str,
        save_output: bool,
        selected_behaviors: Iterable[str] | None = None,
    ) -> str:
        """Build a complete LLM prompt."""
        behavior_names = self.history.normalize_behavior_names(
            list(selected_behaviors or [])
        )
        prompt = [
            "You are an enchanced AI assistant. Your task is to help a "
            "human to find answers to his questions.",
            "Sometimes its coding related question, sometimes some basic "
            "information what they need.",
        ]

        if behavior_names:
            prompt.extend(
                ["===", "Additional system behavior instructions:"]
            )
            for behavior_name in behavior_names:
                prompt.extend(
                    [
                        "===",
                        f"Behavior: {behavior_name}",
                        "===",
                        str(self.behaviors[behavior_name]).strip(),
                    ]
                )

        prompt.extend(
            [
                "===",
                f"The User Input and Question: {user_input}",
                "===",
            ]
        )

        resolved_files = self.filesystem.resolve_selected_files(
            selected_files,
            self.history.path,
        )
        if resolved_files:
            prompt.extend(
                [
                    "===",
                    "This is the list of files and their content as context:",
                ]
            )
            for file_path in resolved_files:
                prompt.extend(
                    [
                        "===",
                        f"filepath: "
                        f"{self.filesystem.relative_path(file_path)}",
                        "===",
                        self.filesystem.read_file(file_path),
                        "===",
                    ]
                )

        if save_output:
            prompt.extend(
                [
                    "The user wants you to save the output into files.",
                    "That requires a strict structure in your response.",
                    "Your response must follow this structure for each file.",
                    "Never return with only the changed part of the code, "
                    "return the full content of the file.",
                    "file_content cannot contain any markdown symbols like "
                    "``` from the beginning and the end.",
                    "===\n===\nfilepath: <path>\n===\n"
                    "<file content>\n===\n",
                ]
            )

        return "\n".join(prompt)