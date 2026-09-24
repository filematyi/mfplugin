from __future__ import annotations

import argparse
import os
import pprint
import threading
from dataclasses import asdict, is_dataclass, replace
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFontDatabase, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mfpy.backend import MfBackend, MfConfig
from mfpy.behaviors.collection import behaviors as REGISTERED_BEHAVIORS
from mfpy.history_diff import DiffReport, build_last_change_comparison
from mfpy.templates.collection import templates as REGISTERED_TEMPLATES


DARK_STYLESHEET = """
QWidget {
    background-color: #111827;
    color: #e5e7eb;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}

QMainWindow {
    background-color: #0b1120;
}

QFrame#Card,
QGroupBox {
    background-color: #151e2e;
    border: 1px solid #263246;
    border-radius: 10px;
}

QGroupBox {
    margin-top: 12px;
    padding: 14px 10px 10px 10px;
    font-weight: 600;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #93c5fd;
}

QLabel#Title {
    color: #f8fafc;
    font-size: 22px;
    font-weight: 700;
}

QLabel#Subtitle,
QLabel#Muted {
    color: #94a3b8;
}

QLabel#StatusBar {
    background-color: #0f172a;
    border-top: 1px solid #263246;
    color: #94a3b8;
    padding: 7px 10px;
}

QLineEdit,
QComboBox,
QPlainTextEdit,
QTreeWidget {
    background-color: #0f172a;
    border: 1px solid #334155;
    border-radius: 7px;
    color: #e5e7eb;
    padding: 7px;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}

QLineEdit:focus,
QComboBox:focus,
QPlainTextEdit:focus,
QTreeWidget:focus {
    border: 1px solid #3b82f6;
}

QComboBox::drop-down {
    border: none;
    width: 28px;
}

QComboBox QAbstractItemView {
    background-color: #172033;
    border: 1px solid #334155;
    color: #e5e7eb;
    selection-background-color: #2563eb;
}

QTreeWidget {
    padding: 0;
    outline: none;
    alternate-background-color: #131d2d;
}

QTreeWidget::item {
    min-height: 30px;
    padding: 2px 6px;
}

QTreeWidget::item:hover {
    background-color: #1e293b;
}

QTreeWidget::item:selected {
    background-color: #1d4ed8;
    color: #ffffff;
}

QHeaderView::section {
    background-color: #1e293b;
    color: #cbd5e1;
    border: none;
    border-right: 1px solid #334155;
    border-bottom: 1px solid #334155;
    padding: 8px;
    font-weight: 600;
}

QPushButton,
QToolButton {
    background-color: #243047;
    border: 1px solid #3a4964;
    border-radius: 7px;
    color: #e5e7eb;
    min-height: 20px;
    padding: 7px 12px;
}

QPushButton:hover,
QToolButton:hover {
    background-color: #334155;
    border-color: #64748b;
}

QPushButton:pressed,
QToolButton:pressed {
    background-color: #1e293b;
}

QPushButton:disabled,
QToolButton:disabled,
QLineEdit:disabled,
QComboBox:disabled,
QCheckBox:disabled {
    color: #64748b;
    background-color: #172033;
    border-color: #263246;
}

QPushButton#PrimaryButton {
    background-color: #2563eb;
    border-color: #3b82f6;
    color: #ffffff;
    font-weight: 700;
    padding: 8px 18px;
}

QPushButton#PrimaryButton:hover {
    background-color: #3b82f6;
}

QPushButton#DangerButton {
    background-color: #3f1d2a;
    border-color: #7f1d1d;
    color: #fecaca;
}

QPushButton#DangerButton:hover {
    background-color: #7f1d1d;
}

QCheckBox {
    spacing: 8px;
}

QCheckBox::indicator {
    width: 17px;
    height: 17px;
}

QMenu {
    background-color: #172033;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 5px;
}

QMenu::item {
    border-radius: 4px;
    padding: 7px 28px 7px 10px;
}

QMenu::item:selected {
    background-color: #2563eb;
}

QProgressBar {
    background-color: #172033;
    border: 1px solid #334155;
    border-radius: 5px;
    height: 9px;
    text-align: center;
}

QProgressBar::chunk {
    background-color: #3b82f6;
    border-radius: 4px;
}

QScrollBar:vertical {
    background: #0f172a;
    border: none;
    width: 12px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #475569;
    border-radius: 6px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background: #64748b;
}

QScrollBar:horizontal {
    background: #0f172a;
    border: none;
    height: 12px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background: #475569;
    border-radius: 6px;
    min-width: 24px;
}

QScrollBar::add-line,
QScrollBar::sub-line {
    width: 0;
    height: 0;
}
"""


class WorkerSignals(QObject):
    submit_complete = pyqtSignal(str, bool)
    diff_complete = pyqtSignal(object)
    revert_complete = pyqtSignal(str)
    operation_failed = pyqtSignal(str, str)


class MfApplication(QMainWindow):
    def __init__(self, folder_path: str, config: MfConfig) -> None:
        super().__init__()

        self.setWindowTitle("MfPlugin")
        self.resize(1100, 800)
        self.setMinimumSize(760, 560)

        self.config_data = config
        self.backend = MfBackend(folder_path, config)
        self.checked_paths: set[str] = set()
        self.busy = False
        self.behavior_actions: dict[str, QAction] = {}

        self.signals = WorkerSignals()
        self.signals.submit_complete.connect(self._submit_complete)
        self.signals.diff_complete.connect(self._diff_complete)
        self.signals.revert_complete.connect(self._revert_complete)
        self.signals.operation_failed.connect(self._operation_failed)

        self._build_ui()
        self.load_folder_state()

    def _build_ui(self) -> None:
        central = QWidget()
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(14, 14, 14, 0)
        root_layout.setSpacing(10)
        self.setCentralWidget(central)

        header_layout = QVBoxLayout()
        header_layout.setSpacing(2)

        title = QLabel("MfPlugin")
        title.setObjectName("Title")
        header_layout.addWidget(title)

        subtitle = QLabel("Project-aware LLM workspace")
        subtitle.setObjectName("Subtitle")
        header_layout.addWidget(subtitle)

        root_layout.addLayout(header_layout)

        project_card = QFrame()
        project_card.setObjectName("Card")
        project_layout = QGridLayout(project_card)
        project_layout.setContentsMargins(14, 14, 14, 14)
        project_layout.setHorizontalSpacing(9)
        project_layout.setVerticalSpacing(10)
        project_layout.setColumnStretch(1, 1)

        project_layout.addWidget(QLabel("Folder"), 0, 0)

        self.folder_entry = QLineEdit(str(self.backend.root))
        self.folder_entry.returnPressed.connect(self.open_folder_from_entry)
        project_layout.addWidget(self.folder_entry, 0, 1)

        self.open_button = QPushButton("Open")
        self.open_button.clicked.connect(self.open_folder_from_entry)
        project_layout.addWidget(self.open_button, 0, 2)

        self.browse_button = QPushButton("Browse…")
        self.browse_button.clicked.connect(self.browse_folder)
        project_layout.addWidget(self.browse_button, 0, 3)

        project_layout.addWidget(QLabel("Model"), 1, 0)

        self.model_entry = QLineEdit(self.config_data.model)
        project_layout.addWidget(self.model_entry, 1, 1, 1, 3)

        project_layout.addWidget(QLabel("Behaviors"), 2, 0)

        self.behavior_button = QToolButton()
        self.behavior_button.setText("None")
        self.behavior_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self.behavior_button.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        behavior_menu = QMenu(self.behavior_button)
        self.behavior_button.setMenu(behavior_menu)

        if REGISTERED_BEHAVIORS:
            for behavior_name in REGISTERED_BEHAVIORS:
                action = behavior_menu.addAction(behavior_name)
                action.setCheckable(True)
                action.toggled.connect(self.update_behavior_label)
                self.behavior_actions[behavior_name] = action
        else:
            action = behavior_menu.addAction("No behaviors registered")
            action.setEnabled(False)
            self.behavior_button.setEnabled(False)

        project_layout.addWidget(self.behavior_button, 2, 1, 1, 3)
        root_layout.addWidget(project_card)

        files_group = QGroupBox("Files and folders")
        files_layout = QVBoxLayout(files_group)
        files_layout.setContentsMargins(10, 16, 10, 10)
        files_layout.setSpacing(8)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Selected", "Path"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.tree.header().setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        self.tree.header().setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.Stretch,
        )
        self.tree.itemChanged.connect(self._tree_item_changed)
        self.tree.installEventFilter(self)
        files_layout.addWidget(self.tree, 1)

        selection_layout = QHBoxLayout()

        self.select_all_button = QPushButton("Select all")
        self.select_all_button.clicked.connect(self.select_all)
        selection_layout.addWidget(self.select_all_button)

        self.clear_selection_button = QPushButton("Clear selection")
        self.clear_selection_button.clicked.connect(self.clear_selection)
        selection_layout.addWidget(self.clear_selection_button)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_entries)
        selection_layout.addWidget(self.refresh_button)

        selection_layout.addStretch()

        self.selection_label = QLabel("0 selected")
        self.selection_label.setObjectName("Muted")
        selection_layout.addWidget(self.selection_label)

        files_layout.addLayout(selection_layout)
        root_layout.addWidget(files_group, 3)

        input_group = QGroupBox("Input / question")
        input_layout = QVBoxLayout(input_group)
        input_layout.setContentsMargins(10, 16, 10, 10)
        input_layout.setSpacing(8)

        template_layout = QHBoxLayout()
        template_layout.addWidget(QLabel("Template"))

        self.template_combo = QComboBox()
        self.template_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.template_combo.addItem("Select a template…", None)

        for template_name in REGISTERED_TEMPLATES:
            self.template_combo.addItem(template_name, template_name)

        if not REGISTERED_TEMPLATES:
            self.template_combo.setEnabled(False)

        self.template_combo.activated.connect(self.apply_template)
        template_layout.addWidget(self.template_combo, 1)
        input_layout.addLayout(template_layout)

        self.input_text = QPlainTextEdit()
        self.input_text.setPlaceholderText(
            "Ask a question or describe the requested changes…"
        )
        self.input_text.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth
        )
        input_layout.addWidget(self.input_text)

        root_layout.addWidget(input_group, 2)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        self.save_checkbox = QCheckBox("Save output into files")
        controls.addWidget(self.save_checkbox)

        self.clear_input_button = QPushButton("Clear input")
        self.clear_input_button.clicked.connect(self.clear_input)
        controls.addWidget(self.clear_input_button)

        controls.addStretch()

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedWidth(140)
        self.progress.setTextVisible(False)
        self.progress.hide()
        controls.addWidget(self.progress)

        self.last_result_button = QPushButton("Show last result")
        self.last_result_button.clicked.connect(self.show_last_result)
        controls.addWidget(self.last_result_button)

        self.diff_button = QPushButton("Show changes")
        self.diff_button.clicked.connect(self.show_last_change_diff)
        controls.addWidget(self.diff_button)

        self.revert_button = QPushButton("Revert last change")
        self.revert_button.setObjectName("DangerButton")
        self.revert_button.clicked.connect(self.revert_last_change)
        controls.addWidget(self.revert_button)

        self.submit_button = QPushButton("Submit")
        self.submit_button.setObjectName("PrimaryButton")
        self.submit_button.clicked.connect(self.submit)
        controls.addWidget(self.submit_button)

        root_layout.addLayout(controls)

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("StatusBar")
        self.status_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        root_layout.addWidget(self.status_label)

        self.submit_shortcut = QShortcut(
            QKeySequence("Ctrl+Return"),
            self,
        )
        self.submit_shortcut.activated.connect(self.submit)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            watched is self.tree
            and event.type() == QEvent.Type.KeyPress
            and event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return)
        ):
            item = self.tree.currentItem()
            if item is not None:
                next_state = (
                    Qt.CheckState.Unchecked
                    if item.checkState(0) == Qt.CheckState.Checked
                    else Qt.CheckState.Checked
                )
                item.setCheckState(0, next_state)
            return True

        return super().eventFilter(watched, event)

    def selected_behavior_names(self) -> list[str]:
        return [
            name
            for name in REGISTERED_BEHAVIORS
            if self.behavior_actions[name].isChecked()
        ]

    def update_behavior_label(self, _checked: bool = False) -> None:
        selected = self.selected_behavior_names()

        if not selected:
            label = "None"
        elif len(selected) <= 2:
            label = ", ".join(selected)
        else:
            label = f"{len(selected)} behaviors selected"

        self.behavior_button.setText(label)

    def apply_template(self, index: int) -> None:
        """Copy the selected template into the editable input field."""
        template_name = self.template_combo.itemData(index)
        if not isinstance(template_name, str):
            return

        content = REGISTERED_TEMPLATES.get(template_name)
        if content is None:
            return

        self.input_text.setPlainText(content.strip())
        self.input_text.setFocus()
        self.set_status(f"Loaded template: {template_name}")

    def browse_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Choose project folder",
            self.folder_entry.text().strip() or os.getcwd(),
        )
        if selected:
            self.folder_entry.setText(selected)
            self.open_folder_from_entry()

    def open_folder_from_entry(self) -> None:
        if self.busy:
            return

        folder = self.folder_entry.text().strip()
        try:
            backend = MfBackend(folder, self.config_data)
        except Exception as error:
            QMessageBox.critical(self, "Invalid folder", str(error))
            return

        self.backend = backend
        self.folder_entry.setText(str(self.backend.root))
        self.load_folder_state()

    def load_folder_state(self) -> None:
        try:
            history = self.backend.load_history()
            self.checked_paths = set(history["selected_files"])
            self.save_checkbox.setChecked(bool(history["save_output"]))

            selected_behaviors = set(
                history.get("selected_behaviors", [])
            )
            for name, action in self.behavior_actions.items():
                action.blockSignals(True)
                action.setChecked(name in selected_behaviors)
                action.blockSignals(False)
            self.update_behavior_label()

            self.input_text.setPlainText(history["user_input"])

            self.refresh_entries()
            self.set_status(f"Loaded {self.backend.root}")
        except Exception as error:
            QMessageBox.critical(self, "Load error", str(error))

    def refresh_entries(self) -> None:
        try:
            existing_checked = set(self.checked_paths)
            entries = self.backend.list_entries()
        except Exception as error:
            QMessageBox.critical(self, "Refresh error", str(error))
            return

        entry_set = set(entries)
        self.checked_paths = existing_checked.intersection(entry_set)

        self.tree.blockSignals(True)
        self.tree.clear()

        folder_color = QColor("#60a5fa")

        for path in entries:
            item = QTreeWidgetItem(["", path])
            item.setData(0, Qt.ItemDataRole.UserRole, path)
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsEnabled
            )
            item.setCheckState(
                0,
                (
                    Qt.CheckState.Checked
                    if path in self.checked_paths
                    else Qt.CheckState.Unchecked
                ),
            )

            if path.endswith("/"):
                item.setForeground(1, folder_color)

            self.tree.addTopLevelItem(item)

        self.tree.blockSignals(False)
        self.update_selection_label()
        self.set_status(f"{len(entries)} entries found")

    def _tree_item_changed(
        self,
        item: QTreeWidgetItem,
        column: int,
    ) -> None:
        if column != 0:
            return

        path = item.data(0, Qt.ItemDataRole.UserRole)
        if not path:
            return

        if item.checkState(0) == Qt.CheckState.Checked:
            self.checked_paths.add(str(path))
        else:
            self.checked_paths.discard(str(path))

        self.update_selection_label()

    def select_all(self) -> None:
        self.tree.blockSignals(True)
        self.checked_paths.clear()

        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if path:
                self.checked_paths.add(str(path))
                item.setCheckState(0, Qt.CheckState.Checked)

        self.tree.blockSignals(False)
        self.update_selection_label()

    def clear_selection(self) -> None:
        self.checked_paths.clear()
        self.tree.blockSignals(True)

        for index in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(index).setCheckState(
                0,
                Qt.CheckState.Unchecked,
            )

        self.tree.blockSignals(False)
        self.update_selection_label()

    def clear_input(self) -> None:
        self.input_text.clear()
        self.template_combo.setCurrentIndex(0)
        self.input_text.setFocus()

    def update_selection_label(self) -> None:
        count = len(self.checked_paths)
        suffix = "" if count == 1 else "s"
        self.selection_label.setText(
            f"{count} selected item{suffix}"
        )

    def set_status(self, status: str) -> None:
        self.status_label.setText(status)

    def set_busy(self, busy: bool, status: str = "") -> None:
        self.busy = busy
        enabled = not busy

        for widget in (
            self.submit_button,
            self.revert_button,
            self.diff_button,
            self.last_result_button,
            self.folder_entry,
            self.model_entry,
            self.save_checkbox,
            self.open_button,
            self.browse_button,
            self.select_all_button,
            self.clear_selection_button,
            self.refresh_button,
            self.clear_input_button,
        ):
            widget.setEnabled(enabled)

        if REGISTERED_BEHAVIORS:
            self.behavior_button.setEnabled(enabled)

        if REGISTERED_TEMPLATES:
            self.template_combo.setEnabled(enabled)

        self.tree.setEnabled(enabled)
        self.input_text.setEnabled(enabled)

        if busy:
            self.progress.show()
        else:
            self.progress.hide()

        if status:
            self.set_status(status)

    def submit(self) -> None:
        if self.busy:
            return

        user_input = self.input_text.toPlainText()
        if not user_input.strip():
            QMessageBox.warning(
                self,
                "Input required",
                "Enter a question or instruction before submitting.",
            )
            return

        model = self.model_entry.text().strip()
        request_config = replace(self.config_data, model=model)

        try:
            request_config.validate()
        except Exception as error:
            QMessageBox.critical(
                self,
                "LLM configuration error",
                str(error),
            )
            return

        self.config_data = request_config
        self.backend.config = request_config

        selected_files = sorted(self.checked_paths)
        selected_behaviors = self.selected_behavior_names()
        save_output = self.save_checkbox.isChecked()

        self.set_busy(True, "Calling the LLM…")

        threading.Thread(
            target=self._submit_worker,
            args=(
                selected_files,
                selected_behaviors,
                user_input,
                save_output,
            ),
            daemon=True,
        ).start()

    def _submit_worker(
        self,
        selected_files: list[str],
        selected_behaviors: list[str],
        user_input: str,
        save_output: bool,
    ) -> None:
        try:
            result = self.backend.build_result(
                selected_files,
                user_input,
                save_output,
                selected_behaviors,
            )
        except Exception as error:
            self.signals.operation_failed.emit(
                "LLM request failed",
                str(error),
            )
            return

        self.signals.submit_complete.emit(result, save_output)

    def _submit_complete(
        self,
        result: str,
        save_output: bool,
    ) -> None:
        self.set_busy(False, "Request completed")

        if save_output:
            self.refresh_entries()

        self.show_result("Results", result)

    def show_last_result(self) -> None:
        """Load and display the latest saved popup content."""
        if self.busy:
            return

        try:
            result = self.backend.load_history().get("last_result", "")
        except Exception as error:
            QMessageBox.critical(
                self,
                "Load last result failed",
                str(error),
            )
            return

        if not isinstance(result, str) or not result:
            QMessageBox.information(
                self,
                "Last result",
                "No saved result found in .mfhist.",
            )
            return

        self.show_result("Last result", result)

    def show_last_change_diff(self) -> None:
        if self.busy:
            return

        self.set_busy(
            True,
            "Comparing files with the previous version…",
        )

        threading.Thread(
            target=self._diff_worker,
            daemon=True,
        ).start()

    def _diff_worker(self) -> None:
        try:
            result = build_last_change_comparison(self.backend)
        except Exception as error:
            self.signals.operation_failed.emit(
                "Show changes failed",
                str(error),
            )
            return

        self.signals.diff_complete.emit(result)

    def _diff_complete(self, result: DiffReport) -> None:
        self.set_busy(False, "Comparison completed")
        self.show_result(
            "Changes",
            self._format_diff_report(result),
            wrap=False,
        )

    def _format_diff_report(self, result: Any) -> str:
        if isinstance(result, str):
            return result

        for attribute in ("text", "content", "diff", "report"):
            value = getattr(result, attribute, None)
            if isinstance(value, str):
                return value

        if is_dataclass(result):
            return pprint.pformat(
                asdict(result),
                width=120,
                sort_dicts=False,
            )

        return str(result)

    def revert_last_change(self) -> None:
        if self.busy:
            return

        answer = QMessageBox.question(
            self,
            "Revert last change",
            "Restore files from the most recent .mfhist backup?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
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
            self.signals.operation_failed.emit(
                "Revert failed",
                str(error),
            )
            return

        self.signals.revert_complete.emit(result)

    def _revert_complete(self, result: str) -> None:
        self.set_busy(False, "Revert completed")
        self.refresh_entries()
        self.show_result("Revert last change", result)

    def _operation_failed(
        self,
        title: str,
        error: str,
    ) -> None:
        self.set_busy(False, error)
        QMessageBox.critical(self, title, error)

    def show_result(
        self,
        title: str,
        content: str,
        wrap: bool = True,
    ) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(900, 650)
        dialog.setMinimumSize(520, 320)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(content)
        text.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth
            if wrap
            else QPlainTextEdit.LineWrapMode.NoWrap
        )

        if not wrap:
            text.setFont(
                QFontDatabase.systemFont(
                    QFontDatabase.SystemFont.FixedFont
                )
            )

        layout.addWidget(text, 1)

        button_layout = QHBoxLayout()

        copy_button = QPushButton("Copy")
        copy_button.clicked.connect(
            lambda: QApplication.clipboard().setText(content)
        )
        button_layout.addWidget(copy_button)

        button_layout.addStretch()

        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        button_layout.addWidget(close_button)

        layout.addLayout(button_layout)
        dialog.exec()


def parse_arguments() -> argparse.Namespace:
    environment = MfConfig.from_environment()

    parser = argparse.ArgumentParser(
        description="Standalone PyQt implementation of MfPlugin."
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
        help="Initial LLM model name. Defaults to MFPLUGIN_MODEL.",
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

    selected = QFileDialog.getExistingDirectory(
        None,
        "Choose project folder",
        os.getcwd(),
    )
    return selected or None


def main() -> None:
    arguments = parse_arguments()

    application = QApplication([])
    application.setApplicationName("MfPlugin")
    application.setStyle("Fusion")
    application.setStyleSheet(DARK_STYLESHEET)

    folder = choose_initial_folder(arguments.folder)
    if not folder:
        return

    config = MfConfig(
        url=arguments.url,
        api_key=arguments.api_key,
        model=arguments.model,
        timeout_seconds=max(1, arguments.timeout),
    )

    try:
        window = MfApplication(folder, config)
    except Exception as error:
        QMessageBox.critical(
            None,
            "MfPlugin startup error",
            str(error),
        )
        return

    window.show()
    application.exec()


if __name__ == "__main__":
    main()