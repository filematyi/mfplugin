"""Project filesystem access service."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


DEFAULT_FILE_PATH_BLACKLIST_SUBSTRINGS = [
    ".git",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    ".idea",
    ".vscode",
    ".DS_Store",
    ".mfhist",
]


class FileSystemService:
    """Provide root-confined project filesystem operations."""

    def __init__(
        self,
        root_path: str | os.PathLike[str],
        blacklist_substrings: Iterable[str] | None = None,
    ) -> None:
        """Initialize the service and validate the project root."""
        self.root = Path(root_path).expanduser().resolve()
        if not self.root.is_dir():
            raise ValueError(f"Invalid directory: {self.root}")

        self.blacklist_substrings = list(
            blacklist_substrings
            if blacklist_substrings is not None
            else DEFAULT_FILE_PATH_BLACKLIST_SUBSTRINGS
        )

    def is_blacklisted(self, path: str | os.PathLike[str]) -> bool:
        """Return whether a path matches a blacklist substring."""
        path_text = str(path)
        normalized = os.path.normpath(path_text)
        posix_path = normalized.replace(os.sep, "/")

        return any(
            substring
            and (
                substring in path_text
                or substring in normalized
                or substring in posix_path
            )
            for substring in self.blacklist_substrings
        )

    def list_entries(self, history_path: Path) -> list[str]:
        """List selectable files and directories under the root."""
        entries: list[str] = []

        for walk_root, directories, filenames in os.walk(self.root):
            walk_root_path = Path(walk_root)
            directories[:] = sorted(
                directory
                for directory in directories
                if not self.is_blacklisted(walk_root_path / directory)
            )

            entries.extend(
                (walk_root_path / directory)
                .relative_to(self.root)
                .as_posix()
                + "/"
                for directory in directories
            )

            for filename in sorted(filenames):
                path = walk_root_path / filename
                if path != history_path and not self.is_blacklisted(path):
                    entries.append(path.relative_to(self.root).as_posix())

        return entries

    def resolve_inside_root(self, path: str) -> Path:
        """Resolve a path and reject traversal outside the project root."""
        raw_path = Path(str(path).rstrip("/"))
        resolved = (
            raw_path.resolve()
            if raw_path.is_absolute()
            else (self.root / raw_path).resolve()
        )

        try:
            resolved.relative_to(self.root)
        except ValueError as error:
            raise ValueError(
                f"Path is outside the selected folder: {path}"
            ) from error

        return resolved

    def relative_path(self, path: Path) -> str:
        """Return a project-relative display path."""
        try:
            return path.resolve().relative_to(self.root).as_posix()
        except ValueError:
            return str(path.resolve())

    @staticmethod
    def read_file(path: Path) -> str:
        """Read a text file, replacing invalid UTF-8 bytes."""
        return path.read_text(encoding="utf-8", errors="replace")

    @staticmethod
    def save_file(path: Path, content: str) -> None:
        """Create parent directories and save UTF-8 text."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(content), encoding="utf-8")

    def resolve_selected_files(
        self,
        selected_paths: Iterable[str],
        history_path: Path,
    ) -> list[Path]:
        """Expand selected files and directories into unique files."""
        resolved_files: list[Path] = []
        seen: set[Path] = set()

        def add_file(file_path: Path) -> None:
            resolved = file_path.resolve()
            if (
                resolved in seen
                or resolved == history_path
                or self.is_blacklisted(resolved)
            ):
                return
            seen.add(resolved)
            resolved_files.append(resolved)

        for selected_path in selected_paths:
            selected_text = str(selected_path).strip()
            if not selected_text or self.is_blacklisted(selected_text):
                continue

            absolute_path = self.resolve_inside_root(selected_text)
            if absolute_path.is_file():
                add_file(absolute_path)
                continue

            if absolute_path.is_dir():
                for walk_root, directories, filenames in os.walk(
                    absolute_path
                ):
                    walk_root_path = Path(walk_root)
                    directories[:] = sorted(
                        directory
                        for directory in directories
                        if not self.is_blacklisted(
                            walk_root_path / directory
                        )
                    )
                    for filename in sorted(filenames):
                        file_path = walk_root_path / filename
                        if file_path.is_file():
                            add_file(file_path)
                continue

            raise FileNotFoundError(
                f"Selected path does not exist: {selected_text}"
            )

        return resolved_files