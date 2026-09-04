from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    try:
        from .backend import MfBackend
    except ImportError:
        from backend import MfBackend


DiffKind = Literal[
    "equal",
    "insert",
    "delete",
    "replace",
    "separator",
    "information",
]


@dataclass(slots=True)
class DiffRow:
    """One aligned row in a side-by-side diff."""

    kind: DiffKind
    previous_number: int | None = None
    previous_text: str = ""
    current_number: int | None = None
    current_text: str = ""
    previous_spans: list[tuple[int, int]] = field(default_factory=list)
    current_spans: list[tuple[int, int]] = field(default_factory=list)


@dataclass(slots=True)
class FileComparison:
    """Comparison data for one changed file."""

    path: str
    status: Literal["Added", "Deleted", "Modified"]
    previous_existed: bool
    current_existed: bool
    previous_content: str
    current_content: str
    rows: list[DiffRow]

    def unified_diff(self) -> str:
        previous_name = self.path if self.previous_existed else "/dev/null"
        current_name = self.path if self.current_existed else "/dev/null"

        lines = difflib.unified_diff(
            self.previous_content.splitlines(),
            self.current_content.splitlines(),
            fromfile=previous_name,
            tofile=current_name,
            lineterm="",
        )
        return "\n".join(lines)


@dataclass(slots=True)
class DiffReport:
    """Structured representation of the most recent file changes."""

    changed_at: str = ""
    files: list[FileComparison] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    no_history: bool = False

    @property
    def has_changes(self) -> bool:
        return bool(self.files)

    def summary(self) -> str:
        if self.no_history:
            return "No last change found in .mfhist."

        if not self.files:
            return (
                "No differences found between the current codebase and "
                "the previous version stored in .mfhist."
            )

        added = sum(file.status == "Added" for file in self.files)
        deleted = sum(file.status == "Deleted" for file in self.files)
        modified = sum(file.status == "Modified" for file in self.files)

        parts: list[str] = []
        if modified:
            parts.append(f"{modified} modified")
        if added:
            parts.append(f"{added} added")
        if deleted:
            parts.append(f"{deleted} deleted")

        return ", ".join(parts)

    def unified_diff(self) -> str:
        """Return a copy-friendly traditional unified diff."""

        lines: list[str] = []

        if self.changed_at:
            lines.extend((f"Last change: {self.changed_at}", ""))

        file_diffs = [
            file.unified_diff()
            for file in self.files
            if file.unified_diff()
        ]

        if file_diffs:
            lines.append("\n\n".join(file_diffs))
        else:
            lines.append(self.summary())

        if self.warnings:
            lines.extend(("", "Warnings:", *self.warnings))

        return "\n".join(lines)


def _changed_spans(
    previous_text: str,
    current_text: str,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Find character ranges changed inside a pair of modified lines."""

    previous_spans: list[tuple[int, int]] = []
    current_spans: list[tuple[int, int]] = []

    matcher = difflib.SequenceMatcher(
        None,
        previous_text,
        current_text,
        autojunk=False,
    )

    for tag, previous_start, previous_end, current_start, current_end in (
        matcher.get_opcodes()
    ):
        if tag == "equal":
            continue

        if previous_start != previous_end:
            previous_spans.append((previous_start, previous_end))
        if current_start != current_end:
            current_spans.append((current_start, current_end))

    return previous_spans, current_spans


def _build_rows(
    previous_content: str,
    current_content: str,
) -> list[DiffRow]:
    """Build aligned rows with three unchanged context lines per change."""

    previous_lines = previous_content.splitlines()
    current_lines = current_content.splitlines()

    matcher = difflib.SequenceMatcher(
        None,
        previous_lines,
        current_lines,
        autojunk=False,
    )
    groups = list(matcher.get_grouped_opcodes(n=3))

    rows: list[DiffRow] = []

    for group_index, group in enumerate(groups):
        if group_index:
            rows.append(DiffRow(kind="separator"))

        for tag, old_start, old_end, new_start, new_end in group:
            if tag == "equal":
                for offset in range(old_end - old_start):
                    rows.append(
                        DiffRow(
                            kind="equal",
                            previous_number=old_start + offset + 1,
                            previous_text=previous_lines[old_start + offset],
                            current_number=new_start + offset + 1,
                            current_text=current_lines[new_start + offset],
                        )
                    )
                continue

            if tag == "delete":
                for old_index in range(old_start, old_end):
                    rows.append(
                        DiffRow(
                            kind="delete",
                            previous_number=old_index + 1,
                            previous_text=previous_lines[old_index],
                        )
                    )
                continue

            if tag == "insert":
                for new_index in range(new_start, new_end):
                    rows.append(
                        DiffRow(
                            kind="insert",
                            current_number=new_index + 1,
                            current_text=current_lines[new_index],
                        )
                    )
                continue

            old_count = old_end - old_start
            new_count = new_end - new_start

            for offset in range(max(old_count, new_count)):
                old_index = old_start + offset
                new_index = new_start + offset
                has_previous = old_index < old_end
                has_current = new_index < new_end

                previous_text = (
                    previous_lines[old_index] if has_previous else ""
                )
                current_text = (
                    current_lines[new_index] if has_current else ""
                )

                if has_previous and has_current:
                    previous_spans, current_spans = _changed_spans(
                        previous_text,
                        current_text,
                    )
                    kind: DiffKind = "replace"
                elif has_previous:
                    previous_spans = []
                    current_spans = []
                    kind = "delete"
                else:
                    previous_spans = []
                    current_spans = []
                    kind = "insert"

                rows.append(
                    DiffRow(
                        kind=kind,
                        previous_number=(
                            old_index + 1 if has_previous else None
                        ),
                        previous_text=previous_text,
                        current_number=(
                            new_index + 1 if has_current else None
                        ),
                        current_text=current_text,
                        previous_spans=previous_spans,
                        current_spans=current_spans,
                    )
                )

    if not rows and previous_content != current_content:
        rows.append(
            DiffRow(
                kind="information",
                previous_text="(empty file)",
                current_text="(empty file)",
            )
        )

    return rows


def _compare_file(
    display_path: str,
    previous_content: str,
    previous_existed: bool,
    current_path: Path,
) -> FileComparison | None:
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
        return None

    if not previous_existed and current_existed:
        status: Literal["Added", "Deleted", "Modified"] = "Added"
    elif previous_existed and not current_existed:
        status = "Deleted"
    else:
        status = "Modified"

    rows = _build_rows(previous_content, current_content)

    if not rows:
        rows.append(
            DiffRow(
                kind="information",
                previous_text=(
                    "(file did not exist)"
                    if not previous_existed
                    else "(empty file)"
                ),
                current_text=(
                    "(file does not exist)"
                    if not current_existed
                    else "(empty file)"
                ),
            )
        )

    return FileComparison(
        path=display_path,
        status=status,
        previous_existed=previous_existed,
        current_existed=current_existed,
        previous_content=previous_content,
        current_content=current_content,
        rows=rows,
    )


def build_last_change_comparison(backend: MfBackend) -> DiffReport:
    """Compare current files with the latest backups in ``.mfhist``."""

    history = backend.load_history()
    last_change = history.get("last_change", {})

    if not isinstance(last_change, dict):
        return DiffReport(no_history=True)

    files = last_change.get("files", [])
    if not isinstance(files, list) or not files:
        return DiffReport(no_history=True)

    changed_at_value = last_change.get("changed_at", "")
    changed_at = (
        changed_at_value
        if isinstance(changed_at_value, str)
        else str(changed_at_value)
    )

    report = DiffReport(changed_at=changed_at)
    seen: set[Path] = set()

    for item in files:
        if not isinstance(item, dict):
            report.warnings.append(
                "Ignored an invalid file record in .mfhist."
            )
            continue

        stored_path = str(item.get("path", "")).strip()
        if not stored_path:
            report.warnings.append(
                "Ignored a file record without a path."
            )
            continue

        try:
            absolute_path = backend.resolve_inside_root(stored_path)
            normalized_path = absolute_path.resolve()
            display_path = backend.relative_path(absolute_path)

            if normalized_path in seen:
                continue
            seen.add(normalized_path)

            if absolute_path == backend.history_path:
                report.warnings.append(
                    f"{display_path}: refusing to compare .mfhist itself"
                )
                continue

            if absolute_path.exists() and not absolute_path.is_file():
                report.warnings.append(
                    f"{display_path}: current path is not a regular file"
                )
                continue

            previous_existed = bool(item.get("existed", True))
            previous_content = item.get("content", "")
            if not isinstance(previous_content, str):
                previous_content = str(previous_content)

            comparison = _compare_file(
                display_path,
                previous_content,
                previous_existed,
                absolute_path,
            )
            if comparison is not None:
                report.files.append(comparison)
        except Exception as error:
            report.warnings.append(f"{stored_path}: {error}")

    return report


def build_last_change_diff(backend: MfBackend) -> str:
    """Backward-compatible textual representation of the comparison."""

    return build_last_change_comparison(backend).unified_diff()