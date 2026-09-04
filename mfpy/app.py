from __future__ import annotations

import argparse
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from .backend import MfBackend, MfConfig
    from .diff_view import show_diff_report
    from .history_diff import DiffReport, build_last_change_comparison
except ImportError:
    from backend import MfBackend, MfConfig
    from diff_view import show_diff_report
    from history_diff import DiffReport, build_last_change_comparison


class MfApplication(tk.Tk):
    def __init__(self, folder_path: str, config: MfConfig) -> None:
        super().__init__()

        self.title("MfPlugin")
        self.geometry("1050x760")
        self.minsize(720, 520)

        self.config_data = config
        self.backend = MfBackend(folder_path, config)
        self.checked_paths: set[str] = set()
        self.busy = False

        self.folder_var = tk.StringVar(value=str(self.backend.root))
        self.save_output_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Ready")

        self._configure_styles()
        self._build_ui()
        self.load_folder_state()

        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.configure("Treeview", rowheight=25)
        style.configure("Primary.TButton", padding=(12, 7))

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=3)
        self.rowconfigure(3, weight=2)

        folder_frame = ttk.Frame(self, padding=(10, 10, 10, 5))
        folder_frame.grid(row=0, column=0, sticky="ew")
        folder_frame.columnconfigure(1, weight=1)

        ttk.Label(folder_frame, text="Folder:").grid(
            row=0, column=0, padx=(0, 8)
        )
        self.folder_entry = ttk.Entry(
            folder_frame,
            textvariable=self.folder_var,
        )
        self.folder_entry.grid(row=0, column=1, sticky="ew")

        ttk.Button(
            folder_frame,
            text="Open",
            command=self.open_folder_from_entry,
        ).grid(row=0, column=2, padx=(8, 0))

        ttk.Button(
            folder_frame,
            text="Browse…",
            command=self.browse_folder,
        ).grid(row=0, column=3, padx=(8, 0))

        files_frame = ttk.LabelFrame(
            self,
            text="Files and folders",
            padding=8,
        )
        files_frame.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=10,
            pady=5,
        )
        files_frame.columnconfigure(0, weight=1)
        files_frame.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            files_frame,
            columns=("selected", "path"),
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("selected", text="Selected")
        self.tree.heading("path", text="Path")
        self.tree.column(
            "selected",
            width=80,
            minwidth=70,
            stretch=False,
            anchor="center",
        )
        self.tree.column("path", width=800, anchor="w")

        tree_scrollbar = ttk.Scrollbar(
            files_frame,
            orient="vertical",
            command=self.tree.yview,
        )
        self.tree.configure(yscrollcommand=tree_scrollbar.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scrollbar.grid(row=0, column=1, sticky="ns")

        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<space>", self.on_tree_space)
        self.tree.bind("<Return>", self.on_tree_space)

        selection_buttons = ttk.Frame(self, padding=(10, 0, 10, 5))
        selection_buttons.grid(row=2, column=0, sticky="ew")

        ttk.Button(
            selection_buttons,
            text="Select all",
            command=self.select_all,
        ).pack(side="left")
        ttk.Button(
            selection_buttons,
            text="Clear selection",
            command=self.clear_selection,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            selection_buttons,
            text="Refresh",
            command=self.refresh_entries,
        ).pack(side="left", padx=(8, 0))

        self.selection_label = ttk.Label(
            selection_buttons,
            text="0 selected",
        )
        self.selection_label.pack(side="right")

        input_frame = ttk.LabelFrame(
            self,
            text="Input / question",
            padding=8,
        )
        input_frame.grid(
            row=3,
            column=0,
            sticky="nsew",
            padx=10,
            pady=5,
        )
        input_frame.columnconfigure(0, weight=1)
        input_frame.rowconfigure(0, weight=1)

        self.input_text = tk.Text(
            input_frame,
            wrap="word",
            undo=True,
            height=9,
        )
        input_scrollbar = ttk.Scrollbar(
            input_frame,
            orient="vertical",
            command=self.input_text.yview,
        )
        self.input_text.configure(yscrollcommand=input_scrollbar.set)
        self.input_text.grid(row=0, column=0, sticky="nsew")
        input_scrollbar.grid(row=0, column=1, sticky="ns")

        controls = ttk.Frame(self, padding=10)
        controls.grid(row=4, column=0, sticky="ew")
        controls.columnconfigure(2, weight=1)

        self.save_checkbox = ttk.Checkbutton(
            controls,
            text="Save output into files",
            variable=self.save_output_var,
        )
        self.save_checkbox.grid(row=0, column=0, sticky="w")

        ttk.Button(
            controls,
            text="Clear input",
            command=self.clear_input,
        ).grid(row=0, column=1, padx=(12, 0))

        self.progress = ttk.Progressbar(
            controls,
            mode="indeterminate",
            length=150,
        )
        self.progress.grid(row=0, column=2, padx=15, sticky="e")

        self.diff_button = ttk.Button(
            controls,
            text="Show changes",
            command=self.show_last_change_diff,
        )
        self.diff_button.grid(row=0, column=3, padx=(0, 8))

        self.revert_button = ttk.Button(
            controls,
            text="Revert last change",
            command=self.revert_last_change,
        )
        self.revert_button.grid(row=0, column=4, padx=(0, 8))

        self.submit_button = ttk.Button(
            controls,
            text="Submit",
            style="Primary.TButton",
            command=self.submit,
        )
        self.submit_button.grid(row=0, column=5)

        status_bar = ttk.Label(
            self,
            textvariable=self.status_var,
            relief="sunken",
            anchor="w",
            padding=(8, 4),
        )
        status_bar.grid(row=5, column=0, sticky="ew")

        self.bind("<Control-Return>", lambda _event: self.submit())

    def browse_folder(self) -> None:
        selected = filedialog.askdirectory(
            parent=self,
            initialdir=self.folder_var.get() or os.getcwd(),
            title="Choose project folder",
        )
        if selected:
            self.folder_var.set(selected)
            self.open_folder_from_entry()

    def open_folder_from_entry(self) -> None:
        if self.busy:
            return

        folder = self.folder_var.get().strip()
        try:
            backend = MfBackend(folder, self.config_data)
        except Exception as error:
            messagebox.showerror(
                "Invalid folder",
                str(error),
                parent=self,
            )
            return

        self.backend = backend
        self.folder_var.set(str(self.backend.root))
        self.load_folder_state()

    def load_folder_state(self) -> None:
        try:
            history = self.backend.load_history()
            self.checked_paths = set(history["selected_files"])
            self.save_output_var.set(bool(history["save_output"]))

            self.input_text.delete("1.0", "end")
            self.input_text.insert("1.0", history["user_input"])

            self.refresh_entries()
            self.status_var.set(f"Loaded {self.backend.root}")
        except Exception as error:
            messagebox.showerror(
                "Load error",
                str(error),
                parent=self,
            )

    def refresh_entries(self) -> None:
        existing_checked = set(self.checked_paths)
        entries = self.backend.list_entries()
        entry_set = set(entries)

        self.checked_paths = existing_checked.intersection(entry_set)
        self.tree.delete(*self.tree.get_children())

        for index, path in enumerate(entries):
            kind = "Folder" if path.endswith("/") else "File"
            marker = "☑" if path in self.checked_paths else "☐"
            self.tree.insert(
                "",
                "end",
                iid=f"entry-{index}",
                values=(marker, path),
                tags=(kind,),
            )

        self.tree.tag_configure("Folder", foreground="#345995")
        self.update_selection_label()
        self.status_var.set(f"{len(entries)} entries found")

    def path_for_item(self, item: str) -> str | None:
        if not item:
            return None

        values = self.tree.item(item, "values")
        if len(values) < 2:
            return None
        return str(values[1])

    def toggle_item(self, item: str) -> None:
        path = self.path_for_item(item)
        if path is None:
            return

        if path in self.checked_paths:
            self.checked_paths.remove(path)
            marker = "☐"
        else:
            self.checked_paths.add(path)
            marker = "☑"

        self.tree.set(item, "selected", marker)
        self.tree.focus(item)
        self.tree.selection_set(item)
        self.update_selection_label()

    def on_tree_click(self, event: tk.Event) -> str | None:
        item = self.tree.identify_row(event.y)
        region = self.tree.identify_region(event.x, event.y)

        if item and region in {"cell", "tree"}:
            self.toggle_item(item)
            return "break"

        return None

    def on_tree_space(self, _event: tk.Event) -> str:
        item = self.tree.focus()
        if item:
            self.toggle_item(item)
        return "break"

    def select_all(self) -> None:
        for item in self.tree.get_children():
            path = self.path_for_item(item)
            if path is not None:
                self.checked_paths.add(path)
                self.tree.set(item, "selected", "☑")
        self.update_selection_label()

    def clear_selection(self) -> None:
        self.checked_paths.clear()
        for item in self.tree.get_children():
            self.tree.set(item, "selected", "☐")
        self.update_selection_label()

    def clear_input(self) -> None:
        self.input_text.delete("1.0", "end")
        self.input_text.focus_set()

    def update_selection_label(self) -> None:
        count = len(self.checked_paths)
        suffix = "" if count == 1 else "s"
        self.selection_label.configure(
            text=f"{count} selected item{suffix}"
        )

    def set_busy(self, busy: bool, status: str = "") -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"

        self.submit_button.configure(state=state)
        self.revert_button.configure(state=state)
        self.diff_button.configure(state=state)
        self.folder_entry.configure(state=state)
        self.save_checkbox.configure(state=state)

        if busy:
            self.progress.start(10)
        else:
            self.progress.stop()

        if status:
            self.status_var.set(status)

    def submit(self) -> None:
        if self.busy:
            return

        user_input = self.input_text.get("1.0", "end-1c")
        if not user_input.strip():
            messagebox.showwarning(
                "Input required",
                "Enter a question or instruction before submitting.",
                parent=self,
            )
            return

        try:
            self.config_data.validate()
        except Exception as error:
            messagebox.showerror(
                "LLM configuration error",
                str(error),
                parent=self,
            )
            return

        selected_files = sorted(self.checked_paths)
        save_output = self.save_output_var.get()

        self.set_busy(True, "Calling the LLM…")

        threading.Thread(
            target=self._submit_worker,
            args=(selected_files, user_input, save_output),
            daemon=True,
        ).start()

    def _submit_worker(
        self,
        selected_files: list[str],
        user_input: str,
        save_output: bool,
    ) -> None:
        try:
            result = self.backend.build_result(
                selected_files,
                user_input,
                save_output,
            )
        except Exception as error:
            self.after(0, self._operation_failed, "LLM request failed", error)
            return

        self.after(0, self._submit_complete, result, save_output)

    def _submit_complete(
        self,
        result: str,
        save_output: bool,
    ) -> None:
        self.set_busy(False, "Request completed")

        if save_output:
            self.refresh_entries()

        self.show_result("Results", result)

    def show_last_change_diff(self) -> None:
        if self.busy:
            return

        self.set_busy(True, "Comparing files with the previous version…")

        threading.Thread(
            target=self._diff_worker,
            daemon=True,
        ).start()

    def _diff_worker(self) -> None:
        try:
            result = build_last_change_comparison(self.backend)
        except Exception as error:
            self.after(
                0,
                self._operation_failed,
                "Show changes failed",
                error,
            )
            return

        self.after(0, self._diff_complete, result)

    def _diff_complete(self, result: DiffReport) -> None:
        self.set_busy(False, "Comparison completed")
        show_diff_report(self, result)

    def revert_last_change(self) -> None:
        if self.busy:
            return

        if not messagebox.askyesno(
            "Revert last change",
            "Restore files from the most recent .mfhist backup?",
            parent=self,
        ):
            return

        self.set_busy(True, "Reverting the last change…")

        threading.Thread(
            target=self._revert_worker,
            daemon=True,
        ).start()

    def _revert_worker(self) -> None:
        try:
            result = self.backend.revert_last_change()
        except Exception as error:
            self.after(0, self._operation_failed, "Revert failed", error)
            return

        self.after(0, self._revert_complete, result)

    def _revert_complete(self, result: str) -> None:
        self.set_busy(False, "Revert completed")
        self.refresh_entries()
        self.show_result("Revert last change", result)

    def _operation_failed(
        self,
        title: str,
        error: Exception,
    ) -> None:
        self.set_busy(False, str(error))
        messagebox.showerror(title, str(error), parent=self)

    def show_result(
        self,
        title: str,
        content: str,
        wrap: str = "word",
    ) -> None:
        window = tk.Toplevel(self)
        window.title(title)
        window.geometry("900x650")
        window.minsize(500, 300)
        window.transient(self)

        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)

        text = tk.Text(
            window,
            wrap=wrap,
            padx=10,
            pady=10,
            font=(
                "TkFixedFont"
                if wrap == "none"
                else "TkDefaultFont"
            ),
        )
        vertical = ttk.Scrollbar(
            window,
            orient="vertical",
            command=text.yview,
        )
        horizontal = ttk.Scrollbar(
            window,
            orient="horizontal",
            command=text.xview,
        )
        text.configure(
            yscrollcommand=vertical.set,
            xscrollcommand=horizontal.set,
        )

        text.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")

        text.insert("1.0", content)
        text.configure(state="disabled")

        button_frame = ttk.Frame(window, padding=8)
        button_frame.grid(row=2, column=0, columnspan=2, sticky="ew")

        ttk.Button(
            button_frame,
            text="Copy",
            command=lambda: self.copy_to_clipboard(content),
        ).pack(side="left")

        ttk.Button(
            button_frame,
            text="Close",
            command=window.destroy,
        ).pack(side="right")

        window.bind("<Escape>", lambda _event: window.destroy())

    def copy_to_clipboard(self, content: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(content)
        self.update()


def parse_arguments() -> argparse.Namespace:
    environment = MfConfig.from_environment()

    parser = argparse.ArgumentParser(
        description="Standalone Tkinter implementation of MfPlugin."
    )
    parser.add_argument(
        "folder",
        nargs="?",
        help="Project folder. A folder dialog opens when omitted.",
    )
    parser.add_argument(
        "--url",
        default=environment.url,
        help="LLM endpoint URL. Defaults to MFPLUGIN_URL.",
    )
    parser.add_argument(
        "--api-key",
        default=environment.api_key,
        help="LLM API key. Defaults to MFPLUGIN_API_KEY.",
    )
    parser.add_argument(
        "--model",
        default=environment.model,
        help="LLM model name. Defaults to MFPLUGIN_MODEL.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=environment.timeout_seconds,
        help="Request timeout in seconds.",
    )
    return parser.parse_args()


def choose_initial_folder(folder: str | None) -> str | None:
    if folder:
        return str(Path(folder).expanduser())

    chooser = tk.Tk()
    chooser.withdraw()

    try:
        selected = filedialog.askdirectory(
            parent=chooser,
            initialdir=os.getcwd(),
            title="Choose project folder",
        )
    finally:
        chooser.destroy()

    return selected or None


def main() -> None:
    arguments = parse_arguments()
    folder = choose_initial_folder(arguments.folder)

    if not folder:
        return
    print(arguments)
    config = MfConfig(
        url=arguments.url,
        api_key=arguments.api_key,
        model=arguments.model,
        timeout_seconds=max(1, arguments.timeout),
    )

    try:
        application = MfApplication(folder, config)
    except Exception as error:
        error_root = tk.Tk()
        error_root.withdraw()
        messagebox.showerror(
            "MfPlugin startup error",
            str(error),
            parent=error_root,
        )
        error_root.destroy()
        return

    application.mainloop()


if __name__ == "__main__":
    main()
