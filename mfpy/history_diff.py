from __future__ import annotations

import difflib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    try:
        from .backend import MfBackend
    except ImportError:
        from backend import MfBackend


def _unified_file_diff(
    display_path: str,
    previous_content: str,
    previous_existed: bool,
    current_path: Path,
) -> str:
    current_existed = current_path.is_file()

    if current_existed:
        current_content = current_path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    else:
        current_content = ""

    if (
        previous_existed == current_existed
        and previous_content == current_content
    ):
        return ""

    previous_lines = previous_content.splitlines()
    current_lines = current_content.splitlines()

    previous_name = display_path if previous_existed else "/dev/null"
    current_name = display_path if current_existed else "/dev/null"

    lines = difflib.unified_diff(
        previous_lines,
        current_lines,
        fromfile=previous_name,
        tofile=current_name,
        lineterm="",
    )
    return "\n".join(lines)


def build_last_change_diff(backend: MfBackend) -> str:
    """Compare the current files with their backups in .mfhist.

    Only files recorded in the most recent ``last_change`` entry are
    inspected. The generated unified diff is oriented from the previous
    version to the current codebase.
    """

    history = backend.load_history()
    last_change = history.get("last_change", {})

    if not isinstance(last_change, dict):
        return "No last change found in .mfhist."

    files = last_change.get("files", [])
    if not isinstance(files, list) or not files:
        return "No last change found in .mfhist."

    changed_at = last_change.get("changed_at", "")
    changed_at = changed_at if isinstance(changed_at, str) else str(changed_at)

    diffs: list[str] = []
    errors: list[str] = []
    seen: set[Path] = set()

    for item in files:
        if not isinstance(item, dict):
            errors.append("Ignored an invalid file record in .mfhist.")
            continue

        stored_path = str(item.get("path", "")).strip()
        if not stored_path:
            errors.append("Ignored a file record without a path.")
            continue

        try:
            absolute_path = backend.resolve_inside_root(stored_path)
            normalized_path = absolute_path.resolve()
            display_path = backend.relative_path(absolute_path)

            if normalized_path in seen:
                continue
            seen.add(normalized_path)

            if absolute_path == backend.history_path:
                errors.append(
                    f"{display_path}: refusing to compare .mfhist itself"
                )
                continue

            if absolute_path.exists() and not absolute_path.is_file():
                errors.append(
                    f"{display_path}: current path is not a regular file"
                )
                continue

            previous_existed = bool(item.get("existed", True))
            previous_content = item.get("content", "")
            if not isinstance(previous_content, str):
                previous_content = str(previous_content)

            file_diff = _unified_file_diff(
                display_path,
                previous_content,
                previous_existed,
                absolute_path,
            )
            if file_diff:
                diffs.append(file_diff)
        except Exception as error:
            errors.append(f"{stored_path}: {error}")

    lines: list[str] = []

    if changed_at:
        lines.append(f"Last change: {changed_at}")
        lines.append("")

    if diffs:
        lines.append("\n\n".join(diffs))
    else:
        lines.append(
            "No differences found between the current codebase and "
            "the previous version stored in .mfhist."
        )

    if errors:
        lines.extend(["", "Warnings:", *errors])

    return "\n".join(lines)