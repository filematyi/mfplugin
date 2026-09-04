from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

try:
    from .history_diff import DiffReport, DiffRow, FileComparison
except ImportError:
    from history_diff import DiffReport, DiffRow, FileComparison


class DiffWindow(tk.Toplevel):
    """Colored, side-by-side viewer for a structured diff report."""

    BACKGROUND = "#ffffff"
    GUTTER = "#f3f4f6"
    FOREGROUND = "#1f2937"
    MUTED = "#6b7280"

    DELETE_BACKGROUND = "#ffebe9"
    DELETE_STRONG = "#ff8182"
    INSERT_BACKGROUND = "#dafbe1"
    INSERT_STRONG = "#7ee787"
    REPLACE_OLD_BACKGROUND = "#fff1e5"
    REPLACE_NEW_BACKGROUND = "#e6ffec"
    SEPARATOR_BACKGROUND = "#e5e7eb"

    def __init__(
        self,
        parent: tk.Misc,
        report: DiffReport,
    ) -> None:
        super().__init__(parent)

        self.report = report
        self.current_file: FileComparison | None = None
        self._synchronizing_scroll = False

        self.title("Changes from previous version")
        self.geometry("1250x760")
        self.minsize(760, 440)
        self.transient(parent)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._build_header()
        self._build_content()
        self._build_footer()
        self._configure_text_tags()
        self._populate_files()

        self.bind("<Escape>", lambda _event: self.destroy())

    def _build_header(self) -> None:
        header = ttk.Frame(self, padding=(12, 10))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        ttk.Label(
            header,
            text="Last code changes",
            font=("TkDefaultFont", 13, "bold"),
        ).grid(row=0, column=0, sticky="w")

        details = self.report.summary()
        if self.report.changed_at:
            details = f"{details}  •  {self.report.changed_at}"

        ttk.Label(
            header,
            text=details,
            foreground=self.MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))

    def _build_content(self) -> None:
        content = ttk.Panedwindow(self, orient="horizontal")
        content.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=10,
            pady=(0, 6),
        )

        navigation = ttk.Frame(content, width=270)
        navigation.columnconfigure(0, weight=1)
        navigation.rowconfigure(1, weight=1)

        ttk.Label(
            navigation,
            text="Changed files",
            font=("TkDefaultFont", 10, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 5))

        self.file_tree = ttk.Treeview(
            navigation,
            columns=("status",),
            show="tree headings",
            selectmode="browse",
        )
        self.file_tree.heading("#0", text="Path")
        self.file_tree.heading("status", text="Status")
        self.file_tree.column("#0", width=185, minwidth=100)
        self.file_tree.column(
            "status",
            width=75,
            minwidth=65,
            stretch=False,
            anchor="center",
        )

        file_scroll = ttk.Scrollbar(
            navigation,
            orient="vertical",
            command=self.file_tree.yview,
        )
        self.file_tree.configure(yscrollcommand=file_scroll.set)

        self.file_tree.grid(row=1, column=0, sticky="nsew")
        file_scroll.grid(row=1, column=1, sticky="ns")
        self.file_tree.bind("<<TreeviewSelect>>", self._file_selected)

        navigation.rowconfigure(2, weight=0)
        self.warning_label = ttk.Label(
            navigation,
            text="",
            foreground="#9a6700",
            wraplength=245,
            justify="left",
        )
        self.warning_label.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(8, 0),
        )

        comparison = ttk.Frame(content)
        comparison.columnconfigure(0, weight=1)
        comparison.columnconfigure(2, weight=1)
        comparison.rowconfigure(1, weight=1)

        self.previous_heading = ttk.Label(
            comparison,
            text="Previous",
            anchor="center",
            font=("TkDefaultFont", 10, "bold"),
        )
        self.current_heading = ttk.Label(
            comparison,
            text="Current",
            anchor="center",
            font=("TkDefaultFont", 10, "bold"),
        )
        self.previous_heading.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.current_heading.grid(row=0, column=2, sticky="ew", pady=(0, 5))

        self.previous_text = self._create_text(comparison)
        self.current_text = self._create_text(comparison)

        divider = ttk.Separator(comparison, orient="vertical")
        vertical = ttk.Scrollbar(
            comparison,
            orient="vertical",
            command=self._vertical_scroll,
        )
        self.vertical_scrollbar = vertical

        previous_horizontal = ttk.Scrollbar(
            comparison,
            orient="horizontal",
            command=self.previous_text.xview,
        )
        current_horizontal = ttk.Scrollbar(
            comparison,
            orient="horizontal",
            command=self.current_text.xview,
        )

        self.previous_text.configure(
            xscrollcommand=previous_horizontal.set,
            yscrollcommand=self._previous_yview_changed,
        )
        self.current_text.configure(
            xscrollcommand=current_horizontal.set,
            yscrollcommand=self._current_yview_changed,
        )

        self.previous_text.grid(row=1, column=0, sticky="nsew")
        divider.grid(row=0, column=1, rowspan=3, sticky="ns", padx=3)
        self.current_text.grid(row=1, column=2, sticky="nsew")
        vertical.grid(row=1, column=3, sticky="ns")
        previous_horizontal.grid(row=2, column=0, sticky="ew")
        current_horizontal.grid(row=2, column=2, sticky="ew")

        content.add(navigation, weight=0)
        content.add(comparison, weight=1)

        self._bind_wheel(self.previous_text)
        self._bind_wheel(self.current_text)

    def _build_footer(self) -> None:
        footer = ttk.Frame(self, padding=(10, 4, 10, 10))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(1, weight=1)

        ttk.Button(
            footer,
            text="Copy unified diff",
            command=self._copy_unified_diff,
        ).grid(row=0, column=0, sticky="w")

        self.file_summary = ttk.Label(
            footer,
            text="",
            foreground=self.MUTED,
        )
        self.file_summary.grid(row=0, column=1, padx=12, sticky="w")

        ttk.Button(
            footer,
            text="Close",
            command=self.destroy,
        ).grid(row=0, column=2, sticky="e")

    def _create_text(self, parent: tk.Misc) -> tk.Text:
        return tk.Text(
            parent,
            wrap="none",
            undo=False,
            borderwidth=1,
            relief="solid",
            padx=0,
            pady=5,
            font="TkFixedFont",
            background=self.BACKGROUND,
            foreground=self.FOREGROUND,
            insertwidth=0,
            cursor="arrow",
        )

    def _configure_text_tags(self) -> None:
        for text in (self.previous_text, self.current_text):
            text.tag_configure("gutter", background=self.GUTTER)
            text.tag_configure("muted", foreground=self.MUTED)
            text.tag_configure(
                "separator",
                background=self.SEPARATOR_BACKGROUND,
                foreground=self.MUTED,
            )
            text.tag_configure(
                "information",
                background=self.GUTTER,
                foreground=self.MUTED,
            )

        self.previous_text.tag_configure(
            "delete",
            background=self.DELETE_BACKGROUND,
        )
        self.previous_text.tag_configure(
            "replace",
            background=self.REPLACE_OLD_BACKGROUND,
        )
        self.previous_text.tag_configure(
            "strong",
            background=self.DELETE_STRONG,
        )
        self.previous_text.tag_configure(
            "empty-change",
            background=self.DELETE_BACKGROUND,
        )

        self.current_text.tag_configure(
            "insert",
            background=self.INSERT_BACKGROUND,
        )
        self.current_text.tag_configure(
            "replace",
            background=self.REPLACE_NEW_BACKGROUND,
        )
        self.current_text.tag_configure(
            "strong",
            background=self.INSERT_STRONG,
        )
        self.current_text.tag_configure(
            "empty-change",
            background=self.INSERT_BACKGROUND,
        )

    def _populate_files(self) -> None:
        self.file_tree.tag_configure("Added", foreground="#1a7f37")
        self.file_tree.tag_configure("Deleted", foreground="#cf222e")
        self.file_tree.tag_configure("Modified", foreground="#9a6700")

        for index, comparison in enumerate(self.report.files):
            self.file_tree.insert(
                "",
                "end",
                iid=f"file-{index}",
                text=comparison.path,
                values=(comparison.status,),
                tags=(comparison.status,),
            )

        if self.report.warnings:
            count = len(self.report.warnings)
            suffix = "" if count == 1 else "s"
            self.warning_label.configure(
                text=f"⚠ {count} warning{suffix}. "
                "See the copied unified diff for details."
            )

        children = self.file_tree.get_children()
        if children:
            first = children[0]
            self.file_tree.selection_set(first)
            self.file_tree.focus(first)
            self.file_tree.see(first)
            self._show_file(self.report.files[0])
        else:
            self._show_empty_report()

    def _show_empty_report(self) -> None:
        self.previous_heading.configure(text="Previous")
        self.current_heading.configure(text="Current")

        self._set_text_state("normal")
        self.previous_text.delete("1.0", "end")
        self.current_text.delete("1.0", "end")

        message = self.report.summary()
        self.previous_text.insert("1.0", f"\n  {message}\n", "information")
        self.current_text.insert("1.0", f"\n  {message}\n", "information")
        self._set_text_state("disabled")

    def _file_selected(self, _event: tk.Event) -> None:
        selection = self.file_tree.selection()
        if not selection:
            return

        item = selection[0]
        try:
            index = int(item.split("-", 1)[1])
        except (IndexError, ValueError):
            return

        if 0 <= index < len(self.report.files):
            self._show_file(self.report.files[index])

    def _show_file(self, comparison: FileComparison) -> None:
        self.current_file = comparison

        previous_state = (
            "exists" if comparison.previous_existed else "does not exist"
        )
        current_state = (
            "exists" if comparison.current_existed else "does not exist"
        )

        self.previous_heading.configure(
            text=f"Previous — {comparison.path} ({previous_state})"
        )
        self.current_heading.configure(
            text=f"Current — {comparison.path} ({current_state})"
        )

        self._set_text_state("normal")
        self.previous_text.delete("1.0", "end")
        self.current_text.delete("1.0", "end")

        for row in comparison.rows:
            self._insert_row(self.previous_text, row, previous=True)
            self._insert_row(self.current_text, row, previous=False)

        self._set_text_state("disabled")
        self.previous_text.yview_moveto(0)
        self.current_text.yview_moveto(0)
        self.previous_text.xview_moveto(0)
        self.current_text.xview_moveto(0)

        additions = sum(
            row.current_number is not None
            and row.kind in {"insert", "replace"}
            for row in comparison.rows
        )
        deletions = sum(
            row.previous_number is not None
            and row.kind in {"delete", "replace"}
            for row in comparison.rows
        )

        self.file_summary.configure(
            text=(
                f"{comparison.status}  •  "
                f"{additions} added/changed lines  •  "
                f"{deletions} removed/changed lines"
            )
        )

    def _insert_row(
        self,
        text_widget: tk.Text,
        row: DiffRow,
        *,
        previous: bool,
    ) -> None:
        if row.kind == "separator":
            text_widget.insert(
                "end",
                "      ··· unchanged lines ···\n",
                ("separator",),
            )
            return

        number = (
            row.previous_number if previous else row.current_number
        )
        content = row.previous_text if previous else row.current_text
        spans = row.previous_spans if previous else row.current_spans

        marker = self._marker_for(row, previous)
        number_text = str(number) if number is not None else ""
        prefix = f"{number_text:>5} {marker} "

        start = text_widget.index("end-1c")
        line_tags = self._line_tags(row, previous)
        text_widget.insert("end", prefix + content + "\n", line_tags)

        prefix_end = f"{start}+{len(prefix)}c"
        text_widget.tag_add("gutter", start, prefix_end)

        if number is None and row.kind in {
            "insert",
            "delete",
            "replace",
        }:
            text_widget.tag_add(
                "empty-change",
                start,
                f"{start} lineend+1c",
            )

        for span_start, span_end in spans:
            text_widget.tag_add(
                "strong",
                f"{prefix_end}+{span_start}c",
                f"{prefix_end}+{span_end}c",
            )

    @staticmethod
    def _marker_for(row: DiffRow, previous: bool) -> str:
        if previous and row.kind in {"delete", "replace"}:
            return "−"
        if not previous and row.kind in {"insert", "replace"}:
            return "+"
        return " "

    @staticmethod
    def _line_tags(row: DiffRow, previous: bool) -> tuple[str, ...]:
        if row.kind == "information":
            return ("information",)

        if previous:
            if row.kind == "delete":
                return ("delete",)
            if row.kind == "replace":
                return ("replace",)
        else:
            if row.kind == "insert":
                return ("insert",)
            if row.kind == "replace":
                return ("replace",)

        return ()

    def _set_text_state(self, state: str) -> None:
        self.previous_text.configure(state=state)
        self.current_text.configure(state=state)

    def _vertical_scroll(self, *args: str) -> None:
        self.previous_text.yview(*args)
        self.current_text.yview(*args)

    def _previous_yview_changed(self, first: str, last: str) -> None:
        self.vertical_scrollbar.set(first, last)
        self._sync_other_text(self.previous_text, self.current_text, first)

    def _current_yview_changed(self, first: str, last: str) -> None:
        self.vertical_scrollbar.set(first, last)
        self._sync_other_text(self.current_text, self.previous_text, first)

    def _sync_other_text(
        self,
        source: tk.Text,
        target: tk.Text,
        first: str,
    ) -> None:
        if self._synchronizing_scroll:
            return

        target_first = target.yview()[0]
        source_first = float(first)

        if abs(target_first - source_first) < 0.000001:
            return

        self._synchronizing_scroll = True
        try:
            target.yview_moveto(source_first)
        finally:
            self._synchronizing_scroll = False

    def _bind_wheel(self, widget: tk.Text) -> None:
        def scroll(event: tk.Event) -> str:
            if getattr(event, "num", None) == 4:
                units = -3
            elif getattr(event, "num", None) == 5:
                units = 3
            else:
                delta = getattr(event, "delta", 0)
                units = -1 * int(delta / 120) if delta else 0

            if units:
                self.previous_text.yview_scroll(units, "units")
                self.current_text.yview_scroll(units, "units")
            return "break"

        widget.bind("<MouseWheel>", scroll)
        widget.bind("<Button-4>", scroll)
        widget.bind("<Button-5>", scroll)

    def _copy_unified_diff(self) -> None:
        content = self.report.unified_diff()
        self.clipboard_clear()
        self.clipboard_append(content)
        self.update()
        self.file_summary.configure(text="Unified diff copied to clipboard")


def show_diff_report(
    parent: tk.Misc,
    report: DiffReport,
) -> DiffWindow:
    """Open and return a colored side-by-side diff window."""

    window = DiffWindow(parent, report)
    window.grab_set()
    window.focus_set()
    return window