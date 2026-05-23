from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QTabBar, QVBoxLayout, QWidget

from core.config_manager import ConfigManager
from core.executor import Executor
from core.models import LauncherConfig, LauncherItem
from core.search_engine import SearchEngine


ALL_GROUP_LABEL = "すべて"
DEFAULT_GROUP_LABEL = "未分類"
EXECUTION_GUARD_SECONDS = 0.4


class LauncherWindow(QWidget):
    def __init__(self, config_manager: ConfigManager, search_engine: SearchEngine, executor: Executor, config: LauncherConfig) -> None:
        super().__init__()
        self.config_manager = config_manager
        self.search_engine = search_engine
        self.executor = executor
        self.config = config
        self.settings_window = None
        self.current_results: list[LauncherItem] = []
        self.current_group = ALL_GROUP_LABEL
        self._last_execution_key = ""
        self._last_execution_time = 0.0

        self.setWindowTitle("プログラム選択")
        self.setWindowFlag(Qt.Window, True)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.resize(720, 420)

        self.group_tabs = QTabBar(self)
        self.group_tabs.setExpanding(False)
        self.group_tabs.currentChanged.connect(self._on_group_changed)

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("登録済みプログラムを検索、またはコマンド入力")
        self.search_input.textChanged.connect(self.refresh_items)
        self.search_input.returnPressed.connect(self.execute_current)

        self.list_widget = QListWidget(self)
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.itemActivated.connect(lambda _: self.execute_current())

        self.guide_label = QLabel("Enter: 実行  Esc: 閉じる  Ctrl+, : 設定", self)

        settings_button = QPushButton("設定", self)
        settings_button.clicked.connect(self.open_settings)

        header = QHBoxLayout()
        header.addWidget(self.search_input)
        header.addWidget(settings_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.group_tabs)
        layout.addLayout(header)
        layout.addWidget(self.list_widget)
        layout.addWidget(self.guide_label)
        self.setLayout(layout)

        self.refresh_items()

    def set_settings_window(self, settings_window) -> None:
        self.settings_window = settings_window

    def refresh_items(self) -> None:
        self.config_manager.normalize_group_order(self.config)
        self._reload_group_tabs()
        query = self.search_input.text()
        visible_items = self._items_for_current_group()
        self.current_results = self.search_engine.search(visible_items, query)
        self.list_widget.clear()
        for item in self.current_results:
            label = f"{item.name} [{item.type}] - {item.description}"
            list_item = QListWidgetItem(label)
            list_item.setData(Qt.UserRole, item.id)
            self.list_widget.addItem(list_item)
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def execute_current(self) -> None:
        query = self.search_input.text().strip()
        item = None
        current = self.list_widget.currentItem()
        if current is not None:
            item_id = current.data(Qt.UserRole)
            item = next((entry for entry in self.current_results if entry.id == item_id), None)

        try:
            if item is not None:
                execution_key = f"item:{item.id}"
                if self._is_duplicate_execution(execution_key):
                    return
                item.touch()
                self.executor.run_item(item)
                self.config_manager.save(self.config)
                self.clear_and_hide()
                return

            if query:
                execution_key = f"query:{query}"
                if self._is_duplicate_execution(execution_key):
                    return
                if self.executor.run_command_text(query, lambda text: self.search_engine.find_exact(self._items_for_current_group(), text)):
                    self.clear_and_hide()
                    return

            QMessageBox.warning(self, "Not found", "一致する候補または実行可能な入力がありません。")
        except Exception as exc:
            QMessageBox.critical(self, "Execution failed", str(exc))

    def open_settings(self) -> None:
        if self.settings_window is None:
            return
        self.settings_window.set_current_group(self.current_group)
        self.settings_window.reload()
        self.settings_window.show()
        self.settings_window.recenter()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def show_launcher(self) -> None:
        self.refresh_items()
        self.show()
        self.raise_()
        self.activateWindow()
        self.search_input.setFocus()
        self.search_input.selectAll()

    def hide_launcher(self) -> None:
        self.hide()

    def clear_and_hide(self) -> None:
        self.search_input.clear()
        self.refresh_items()
        self.hide_launcher()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.hide_launcher()
            event.accept()
            return
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Comma:
            self.open_settings()
            event.accept()
            return
        super().keyPressEvent(event)

    def _group_names(self) -> list[str]:
        groups = list(self.config.group_order)
        if DEFAULT_GROUP_LABEL not in groups:
            groups.append(DEFAULT_GROUP_LABEL)
        return [ALL_GROUP_LABEL, *groups]

    def _reload_group_tabs(self) -> None:
        groups = self._group_names()
        if self.current_group not in groups:
            self.current_group = ALL_GROUP_LABEL

        self.group_tabs.blockSignals(True)
        while self.group_tabs.count() > 0:
            self.group_tabs.removeTab(0)
        current_index = 0
        for index, group in enumerate(groups):
            self.group_tabs.addTab(group)
            if group == self.current_group:
                current_index = index
        self.group_tabs.setCurrentIndex(current_index)
        self.group_tabs.blockSignals(False)

    def _items_for_current_group(self) -> list[LauncherItem]:
        if self.current_group == ALL_GROUP_LABEL:
            return list(self.config.items)
        return [item for item in self.config.items if (item.group or DEFAULT_GROUP_LABEL) == self.current_group]

    def _on_group_changed(self, index: int) -> None:
        if index < 0:
            return
        self.current_group = self.group_tabs.tabText(index)
        self.refresh_items()

    def _is_duplicate_execution(self, execution_key: str) -> bool:
        now = time.monotonic()
        is_duplicate = (
            execution_key == self._last_execution_key
            and (now - self._last_execution_time) < EXECUTION_GUARD_SECONDS
        )
        self._last_execution_key = execution_key
        self._last_execution_time = now
        return is_duplicate
