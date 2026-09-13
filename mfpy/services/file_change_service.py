"""LLM file response parsing, backup, writing, and revert service."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path
from typing import Any

from .filesystem_service import FileSystemService
from .history_service import HistoryService


FILE_BLOCK_PATTERN = re.compile(
    r"(?:^===\s*\n|^)"
    r"filepath:\s*(?P<filepath>[^\n]+)\n"
    r"===\s*\n"
    r"(?P<content>.*?)(?=^===\s*\nfilepath:|^filepath:|\Z)",
    re.MULTILINE | re.DOTALL,
)


class FileChangeService:
    """Apply and revert file changes returned by the LLM."""

    def __init__(
        self,
        filesystem: FileSystemService,
        history: HistoryService,
    ) -> None:
        """Initialize the service dependencies."""
        self.filesystem = filesystem
        self.history = history

    @staticmethod
    def extract_files(text: str) -> dict[str, str]:
        """Extract filepath/content blocks from an LLM response."""
        normalized = textwrap.dedent(text).strip()
        result: dict[str, str] = {}

        for match in FILE_BLOCK_PATTERN.finditer(normalized):
            filename = match.group("filepath").strip()
            content = match.group("content").rstrip()
            if content.endswith("==="):
                content = content[:-3].rstrip()
            result[filename] = content

        return result

    def collect_backups(
        self,
        mapping: dict[str, str],
    ) -> tuple[list[dict], list[tuple[Path, str, str]], list[str]]:
        """Validate output paths and collect their original content."""
        backups: list[dict] = []
        files_to_write: list[tuple[Path, str, str]] = []
        skipped: list[str] = []
        seen: set[Path] = set()

        for path, content in mapping.items():
            try:
                absolute_path = self.filesystem.resolve_inside_root(path)
            except ValueError as error:
                skipped.append(str(error))
                continue

            display_path = self.filesystem.relative_path(absolute_path)
            if absolute_path == self.history.path:
                skipped.append(
                    f"{display_path} skipped because .mfhist is managed "
                    "by the application"
                )
                continue

            normalized = absolute_path.resolve()
            if normalized in seen:
                skipped.append(
                    f"{display_path} skipped because it was duplicated "
                    "in the response"
                )
                continue
            seen.add(normalized)

            if absolute_path.is_dir():
                skipped.append(
                    f"{display_path} skipped because it is a directory"
                )
                continue

            existed = absolute_path.exists()
            original = (
                self.filesystem.read_file(absolute_path) if existed else ""
            )
            backups.append(
                {
                    "path": display_path,
                    "existed": bool(existed),
                    "content": original,
                }
            )
            files_to_write.append(
                (absolute_path, content, display_path)
            )

        return backups, files_to_write, skipped

    def write_files(
        self,
        files_to_write: list[tuple[Path, str, str]],
    ) -> None:
        """Write prepared file changes."""
        for absolute_path, content, _display_path in files_to_write:
            self.filesystem.save_file(absolute_path, content)

    def revert_last_change(self) -> str:
        """Restore files from the last history backup."""
        history = self.history.load()
        last_change = history.get("last_change", {})
        files = (
            last_change.get("files", [])
            if isinstance(last_change, dict)
            else []
        )
        if not files:
            return "No last change found in .mfhist. Nothing to revert."

        restored: list[str] = []
        deleted: list[str] = []
        errors: list[str] = []

        for item in files:
            if isinstance(item, dict):
                self._revert_item(item, restored, deleted, errors)

        if not errors:
            history["last_change"] = {"changed_at": "", "files": []}
            self.history.write(history)

        return self._format_revert_result(restored, deleted, errors)

    def _revert_item(
        self,
        item: dict[str, Any],
        restored: list[str],
        deleted: list[str],
        errors: list[str],
    ) -> None:
        path = str(item.get("path", "")).strip()
        if not path:
            return

        try:
            absolute_path = self.filesystem.resolve_inside_root(path)
            display_path = self.filesystem.relative_path(absolute_path)
            if absolute_path == self.history.path:
                errors.append(
                    f"{display_path}: refusing to modify .mfhist"
                )
                return

            if bool(item.get("existed", True)):
                content = item.get("content", "")
                self.filesystem.save_file(
                    absolute_path,
                    content if isinstance(content, str) else str(content),
                )
                restored.append(display_path)
            elif absolute_path.is_file():
                absolute_path.unlink()
                deleted.append(display_path)
            elif absolute_path.exists():
                errors.append(
                    f"{display_path}: path is not a file and was not deleted"
                )
            else:
                deleted.append(display_path)
        except (OSError, ValueError) as error:
            errors.append(f"{path}: {error}")

    @staticmethod
    def _format_revert_result(
        restored: list[str],
        deleted: list[str],
        errors: list[str],
    ) -> str:
        lines: list[str] = []
        if restored:
            lines.extend(["Files restored:", *restored])
        if deleted:
            if lines:
                lines.append("")
            lines.extend(
                [
                    "Files deleted because they did not exist before the "
                    "last change:",
                    *deleted,
                ]
            )
        if errors:
            if lines:
                lines.append("")
            lines.extend(
                [
                    "Errors:",
                    *errors,
                    "",
                    ".mfhist was kept so you can try reverting again.",
                ]
            )
        else:
            if lines:
                lines.append("")
            lines.extend(
                [
                    "Last change reverted successfully.",
                    ".mfhist input, selected files, selected behaviors, "
                    "and save-output setting were kept, and the consumed "
                    "backup was cleared.",
                ]
            )
        return "\n".join(lines)