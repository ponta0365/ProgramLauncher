from __future__ import annotations

import logging
import os
import re
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QKeySequence
from PySide6.QtWidgets import QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton, QTabBar, QTextEdit, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from core.config_manager import ConfigManager
from core.import_sources import DiscoveredItem, discover_files_in_folder, discover_steam_games, discover_windows_apps, discover_windows_standard_items
from core.models import LauncherConfig, LauncherItem


ALL_GROUP_LABEL = "すべて"
FAVORITES_LABEL = "お気に入り"
DEFAULT_GROUP_LABEL = "未分類"
logger = logging.getLogger(__name__)


class ItemEditor(QDialog):
    def __init__(self, parent: QWidget | None, item: LauncherItem | None = None, groups: list[str] | None = None, default_group: str = DEFAULT_GROUP_LABEL) -> None:
        super().__init__(parent)
        self.setWindowTitle("Item Editor")
        self.resize(520, 400)

        self.name_edit = QLineEdit(item.name if item else "", self)
        self.command_edit = QLineEdit(item.command_name if item else "", self)
        self.aliases_edit = QLineEdit(", ".join(item.aliases) if item else "", self)
        self.type_combo = QComboBox(self)
        self.type_combo.addItems(["app", "ps", "file", "url"])
        if item:
            self.type_combo.setCurrentText(item.type)
        self.group_combo = QComboBox(self)
        group_names = [group for group in (groups or []) if group != ALL_GROUP_LABEL]
        if default_group and default_group not in group_names:
            group_names.append(default_group)
        if item and item.group and item.group not in group_names:
            group_names.append(item.group)
        if DEFAULT_GROUP_LABEL not in group_names:
            group_names.append(DEFAULT_GROUP_LABEL)
        ordered_groups = []
        for group in group_names:
            if group not in ordered_groups:
                ordered_groups.append(group)
        self.group_combo.addItems(ordered_groups)
        self.group_combo.setEditable(True)
        self.group_combo.setCurrentText(item.group if item else default_group)
        self.target_edit = QTextEdit(item.target if item else "", self)
        self.args_edit = QLineEdit(item.args if item else "", self)
        self.workdir_edit = QLineEdit(item.workdir if item else "", self)
        self.description_edit = QLineEdit(item.description if item else "", self)
        self.admin_check = QCheckBox("管理者権限で実行", self)
        self.admin_check.setChecked(item.run_as_admin if item else False)
        self.favorite_check = QCheckBox("お気に入り", self)
        self.favorite_check.setChecked(item.favorite if item else False)

        form = QFormLayout()
        form.addRow("表示名", self.name_edit)
        form.addRow("コマンド名", self.command_edit)
        form.addRow("グループ", self.group_combo)
        form.addRow("別名", self.aliases_edit)
        form.addRow("種別", self.type_combo)
        form.addRow("実行内容", self.target_edit)
        form.addRow("引数", self.args_edit)
        form.addRow("作業フォルダ", self.workdir_edit)
        form.addRow("説明", self.description_edit)
        form.addRow("", self.admin_check)
        form.addRow("", self.favorite_check)

        save_button = QPushButton("保存", self)
        save_button.clicked.connect(self.accept)
        cancel_button = QPushButton("キャンセル", self)
        cancel_button.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(save_button)
        buttons.addWidget(cancel_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(buttons)
        self.setLayout(layout)

    def build_item(self, item_id: str, usage_count: int = 0, last_used: str = "") -> LauncherItem:
        return LauncherItem(
            id=item_id,
            name=self.name_edit.text().strip(),
            command_name=self.command_edit.text().strip(),
            aliases=[part.strip() for part in self.aliases_edit.text().split(",") if part.strip()],
            type=self.type_combo.currentText(),
            target=self.target_edit.toPlainText().strip(),
            args=self.args_edit.text().strip(),
            workdir=self.workdir_edit.text().strip(),
            description=self.description_edit.text().strip(),
            group=self.group_combo.currentText().strip() or DEFAULT_GROUP_LABEL,
            run_as_admin=self.admin_check.isChecked(),
            favorite=self.favorite_check.isChecked(),
            usage_count=usage_count,
            last_used=last_used,
        )


class ImportItemsDialog(QDialog):
    def __init__(self, parent: QWidget | None, groups: list[str], default_group: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("一括登録")
        self.resize(980, 640)
        self._groups = groups
        self._default_group = default_group
        self._all_candidates: list[DiscoveredItem] = []
        self._filtered_candidates: list[DiscoveredItem] = []
        self._selected_keys: set[str] = set()

        self.source_combo = QComboBox(self)
        self.source_combo.addItems(["フォルダ", "Windows アプリ一覧", "Windows 標準項目", "Steam ゲーム一覧"])
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)

        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("名前 / 種別 / 内容で検索")
        self.search_edit.textChanged.connect(self._apply_filter)

        self.folder_edit = QLineEdit(self)
        self.folder_edit.setPlaceholderText("フォルダを選択")
        browse_button = QPushButton("参照", self)
        browse_button.clicked.connect(self._browse_folder)

        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_edit)
        folder_row.addWidget(browse_button)

        self.extensions_edit = QLineEdit(".exe\n.lnk\n.bat\n.cmd\n.ps1", self)
        self.extensions_edit.setPlaceholderText("1行ずつ拡張子を入力")
        self.recursive_check = QCheckBox("サブフォルダも含める", self)
        self.recursive_check.setChecked(True)

        self.group_combo = QComboBox(self)
        self.group_combo.setEditable(True)
        self.group_combo.addItems([group for group in groups if group != ALL_GROUP_LABEL] or [default_group])
        if default_group not in [self.group_combo.itemText(i) for i in range(self.group_combo.count())]:
            self.group_combo.addItem(default_group)
        self.group_combo.setCurrentText(default_group)

        refresh_button = QPushButton("一覧更新", self)
        refresh_button.clicked.connect(self.refresh_candidates)
        select_all_button = QPushButton("全選択", self)
        select_all_button.clicked.connect(self.select_all)
        select_visible_button = QPushButton("表示中のみ選択", self)
        select_visible_button.clicked.connect(self.select_visible)
        clear_button = QPushButton("全解除", self)
        clear_button.clicked.connect(self.clear_selection)
        import_button = QPushButton("登録", self)
        import_button.clicked.connect(self.accept)
        cancel_button = QPushButton("キャンセル", self)
        cancel_button.clicked.connect(self.reject)

        actions = QHBoxLayout()
        actions.addWidget(refresh_button)
        actions.addWidget(select_all_button)
        actions.addWidget(select_visible_button)
        actions.addWidget(clear_button)
        actions.addStretch(1)
        actions.addWidget(import_button)
        actions.addWidget(cancel_button)

        self.table = QTableWidget(self)
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["選択", "名前", "種別", "実行先", "引数", "作業フォルダ", "説明"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemChanged.connect(self._on_item_changed)

        self.summary_label = QLabel("", self)

        form = QFormLayout()
        form.addRow("入力元", self.source_combo)
        form.addRow("検索", self.search_edit)
        form.addRow("フォルダ", folder_row)
        form.addRow("拡張子", self.extensions_edit)
        form.addRow("", self.recursive_check)
        form.addRow("登録先グループ", self.group_combo)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.table)
        layout.addLayout(actions)
        self.setLayout(layout)

        self._update_source_controls()
        self.source_combo.blockSignals(True)
        self.source_combo.setCurrentText("Windows アプリ一覧")
        self.source_combo.blockSignals(False)
        self.refresh_candidates(reset_selection=True)

    def selected_group(self) -> str:
        return self.group_combo.currentText().strip() or self._default_group

    def selected_candidates(self) -> list[DiscoveredItem]:
        selected_rows = []
        for candidate in self._all_candidates:
            if self._candidate_key(candidate) in self._selected_keys:
                selected_rows.append(candidate)
        return selected_rows

    def refresh_candidates(self, reset_selection: bool = False) -> None:
        source = self.source_combo.currentText()
        if source == "フォルダ":
            folder = Path(self.folder_edit.text().strip())
            extensions = self._parse_extensions(self.extensions_edit.text())
            if not folder.exists():
                self._all_candidates = []
            else:
                self._all_candidates = discover_files_in_folder(folder, extensions, self.recursive_check.isChecked()) if extensions else []
        elif source == "Windows アプリ一覧":
            self._all_candidates = discover_windows_apps()
        elif source == "Windows 標準項目":
            self._all_candidates = discover_windows_standard_items()
        else:
            self._all_candidates = discover_steam_games()

        candidate_keys = {self._candidate_key(candidate) for candidate in self._all_candidates}
        if reset_selection:
            self._selected_keys = set(candidate_keys)
        else:
            self._selected_keys.intersection_update(candidate_keys)

        self._apply_filter()

    def select_all(self) -> None:
        self._selected_keys = {self._candidate_key(candidate) for candidate in self._all_candidates}
        self._populate_table()
        self._update_summary()

    def select_visible(self) -> None:
        self._selected_keys.update(self._candidate_key(candidate) for candidate in self._filtered_candidates)
        self._populate_table()
        self._update_summary()

    def clear_selection(self) -> None:
        self._selected_keys.clear()
        self._populate_table()
        self._update_summary()

    def selected_items(self) -> list[DiscoveredItem]:
        return self.selected_candidates()

    def _update_source_controls(self) -> None:
        folder_mode = self.source_combo.currentText() == "フォルダ"
        self.folder_edit.setEnabled(folder_mode)
        self.extensions_edit.setEnabled(folder_mode)
        self.recursive_check.setEnabled(folder_mode)

    def _on_source_changed(self, *_: object) -> None:
        self._update_source_controls()
        self.refresh_candidates(reset_selection=True)

    def _apply_filter(self, *_: object) -> None:
        keyword = self.search_edit.text().strip().lower()
        if keyword:
            self._filtered_candidates = [
                candidate
                for candidate in self._all_candidates
                if keyword in candidate.name.lower()
                or keyword in candidate.type.lower()
                or keyword in candidate.target.lower()
                or keyword in candidate.description.lower()
            ]
        else:
            self._filtered_candidates = list(self._all_candidates)
        self._populate_table()

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "登録元フォルダを選択")
        if folder:
            self.folder_edit.setText(folder)
            self.refresh_candidates(reset_selection=True)

    def _parse_extensions(self, raw_text: str) -> list[str]:
        parts = [part.strip().lower() for part in re.split(r"[,;\s]+", raw_text) if part.strip()]
        extensions = []
        for part in parts:
            extension = part if part.startswith(".") else f".{part}"
            if extension not in extensions:
                extensions.append(extension)
        return extensions

    def _populate_table(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.table.setRowCount(len(self._filtered_candidates))
        for row, candidate in enumerate(self._filtered_candidates):
            candidate_key = self._candidate_key(candidate)
            selector = QTableWidgetItem("")
            selector.setFlags(selector.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            selector.setCheckState(Qt.Checked if candidate_key in self._selected_keys else Qt.Unchecked)
            selector.setData(Qt.UserRole, candidate)
            self.table.setItem(row, 0, selector)

            name_item = QTableWidgetItem(candidate.name)
            type_item = QTableWidgetItem(candidate.type)
            target_item = QTableWidgetItem(candidate.target)
            args_item = QTableWidgetItem(candidate.args)
            workdir_item = QTableWidgetItem(candidate.workdir)
            description_item = QTableWidgetItem(candidate.description)
            self.table.setItem(row, 1, name_item)
            self.table.setItem(row, 2, type_item)
            self.table.setItem(row, 3, target_item)
            self.table.setItem(row, 4, args_item)
            self.table.setItem(row, 5, workdir_item)
            self.table.setItem(row, 6, description_item)

        self.table.resizeColumnsToContents()
        self.table.blockSignals(False)
        self._update_summary()

    def _update_summary(self) -> None:
        total = len(self._all_candidates)
        visible = len(self._filtered_candidates)
        selected = len(self.selected_candidates())
        source = self.source_combo.currentText()
        self.summary_label.setText(f"ソース: {source}  候補: {visible}/{total}  選択: {selected}")

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        candidate = item.data(Qt.UserRole)
        if not isinstance(candidate, DiscoveredItem):
            return
        key = self._candidate_key(candidate)
        if item.checkState() == Qt.Checked:
            self._selected_keys.add(key)
        else:
            self._selected_keys.discard(key)
        self._update_summary()

    def accept(self) -> None:
        if not self.selected_candidates():
            QMessageBox.information(self, "一括登録", "登録する項目を1つ以上選択してください。")
            return
        super().accept()

    def _candidate_key(self, candidate: DiscoveredItem) -> str:
        args = re.sub(r"\s+", " ", candidate.args.strip().lower())
        return f"{candidate.type}:{candidate.target.strip().lower()}|args:{args}"


class SettingsWindow(QWidget):
    def __init__(self, config_manager: ConfigManager, config: LauncherConfig, on_saved) -> None:
        super().__init__()
        self.config_manager = config_manager
        self.config = config
        self.on_saved = on_saved
        self.current_group = ALL_GROUP_LABEL
        self._suspend_auto_save = False

        self.setWindowTitle("Launcher Settings")
        self.setWindowFlag(Qt.Window, True)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setAcceptDrops(True)
        self.resize(900, 620)

        self.hotkey_edit = QLineEdit(self.config.settings.hotkey, self)
        self.alt_double_tap_check = QCheckBox("Alt キーを2回押してプログラム選択を開く", self)
        self.alt_double_tap_check.setChecked(self.config.settings.alt_double_tap)
        self.startup_check = QCheckBox("Windows 起動時に自動起動する", self)
        self.startup_check.setChecked(self.config.settings.launch_on_startup)
        self.log_path_edit = QLineEdit(str(Path(self.config_manager.base_dir) / "logs" / "app.log"), self)
        self.log_path_edit.setReadOnly(True)
        self.save_status_label = QLabel("", self)
        self.save_status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.hotkey_edit.editingFinished.connect(self.auto_save_settings)
        self.alt_double_tap_check.toggled.connect(lambda _: self.auto_save_settings())
        self.startup_check.toggled.connect(lambda _: self.auto_save_settings())

        self.group_tabs = QTabBar(self)
        self.group_tabs.currentChanged.connect(self._on_group_changed)

        self.item_list = QListWidget(self)
        self.item_list.setAcceptDrops(False)
        self.item_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.item_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.item_list.setDefaultDropAction(Qt.MoveAction)
        self.item_list.setDragEnabled(True)
        self.item_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.item_list.customContextMenuRequested.connect(self.show_item_context_menu)
        self.item_list.itemDoubleClicked.connect(lambda _: self.edit_item())
        self.item_list.model().rowsMoved.connect(lambda *_: self.reorder_items_from_view())

        self.drop_hint = QLineEdit("ここに EXE / LNK / PS1 / ファイル / フォルダをドラッグ&ドロップして登録", self)
        self.drop_hint.setReadOnly(True)

        add_group_button = QPushButton("グループ追加", self)
        add_group_button.clicked.connect(self.add_group)
        rename_group_button = QPushButton("グループ名変更", self)
        rename_group_button.clicked.connect(self.rename_group)
        delete_group_button = QPushButton("グループ削除", self)
        delete_group_button.clicked.connect(self.delete_group)
        move_left_button = QPushButton("左へ", self)
        move_left_button.clicked.connect(lambda: self.move_group(-1))
        move_right_button = QPushButton("右へ", self)
        move_right_button.clicked.connect(lambda: self.move_group(1))
        add_button = QPushButton("追加", self)
        add_button.clicked.connect(self.add_item)
        import_folder_button = QPushButton("一括登録", self)
        import_folder_button.clicked.connect(self.open_import_dialog)
        edit_button = QPushButton("編集", self)
        edit_button.clicked.connect(self.edit_item)
        delete_button = QPushButton("削除", self)
        delete_button.clicked.connect(self.delete_item)
        create_backup_button = QPushButton("バックアップ作成", self)
        create_backup_button.clicked.connect(self.create_backup)
        restore_button = QPushButton("復元", self)
        restore_button.clicked.connect(self.restore_backup)
        open_log_button = QPushButton("ログを開く", self)
        open_log_button.clicked.connect(self.open_log_folder)
        save_button = QPushButton("保存", self)
        save_button.clicked.connect(self.save_settings)

        top_form = QFormLayout()
        top_form.addRow("ホットキー", self.hotkey_edit)
        top_form.addRow("", self.alt_double_tap_check)
        top_form.addRow("", self.startup_check)
        top_form.addRow("ログファイル", self.log_path_edit)
        top_form.addRow("ドロップ登録", self.drop_hint)

        buttons = QHBoxLayout()
        buttons.addWidget(add_group_button)
        buttons.addWidget(rename_group_button)
        buttons.addWidget(delete_group_button)
        buttons.addWidget(move_left_button)
        buttons.addWidget(move_right_button)
        buttons.addWidget(add_button)
        buttons.addWidget(import_folder_button)
        buttons.addWidget(edit_button)
        buttons.addWidget(delete_button)
        buttons.addWidget(create_backup_button)
        buttons.addWidget(restore_button)
        buttons.addWidget(open_log_button)
        buttons.addStretch(1)
        buttons.addWidget(self.save_status_label)
        buttons.addWidget(save_button)

        layout = QVBoxLayout(self)
        layout.addLayout(top_form)
        layout.addWidget(self.group_tabs)
        layout.addWidget(self.item_list)
        layout.addLayout(buttons)
        self.setLayout(layout)

        self.reload()

    def set_current_group(self, group: str) -> None:
        if group in {"", FAVORITES_LABEL}:
            self.current_group = ALL_GROUP_LABEL
            return
        self.current_group = group or ALL_GROUP_LABEL

    def recenter(self) -> None:
        self.adjustSize()
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        x = available.x() + max(0, (available.width() - self.width()) // 2)
        y = available.y() + max(0, (available.height() - self.height()) // 2)
        self.move(x, y)

    def reload(self) -> None:
        self.config_manager.normalize_group_order(self.config)
        self._suspend_auto_save = True
        try:
            self.hotkey_edit.setText(self.config.settings.hotkey)
            self.alt_double_tap_check.setChecked(self.config.settings.alt_double_tap)
            self.startup_check.setChecked(self.config.settings.launch_on_startup)
            self._reload_group_tabs()
            self.item_list.clear()
            for item in self._items_for_current_group():
                favorite_mark = "★ " if item.favorite else ""
                row = QListWidgetItem(f"{favorite_mark}{item.command_name} | {item.name} | {item.type} | {item.group}")
                row.setData(Qt.UserRole, item.id)
                self.item_list.addItem(row)
        finally:
            self._suspend_auto_save = False

    def add_group(self) -> None:
        group_name, accepted = QInputDialog.getText(self, "グループ追加", "新しいグループ名")
        if not accepted:
            return
        normalized = group_name.strip()
        if not normalized:
            return
        if normalized not in self.config.group_order:
            self.config.group_order.append(normalized)
        self.current_group = normalized
        self._save_and_reload()

    def rename_group(self) -> None:
        if self.current_group in {ALL_GROUP_LABEL, ""}:
            QMessageBox.information(self, "グループ名変更", "変更したいグループタブを選択してください。")
            return
        group_name, accepted = QInputDialog.getText(self, "グループ名変更", "新しいグループ名", text=self.current_group)
        if not accepted:
            return
        normalized = group_name.strip()
        if not normalized:
            return
        for item in self.config.items:
            if (item.group or DEFAULT_GROUP_LABEL) == self.current_group:
                item.group = normalized
        self.config.group_order = [normalized if group == self.current_group else group for group in self.config.group_order]
        self._dedupe_group_order()
        self.current_group = normalized
        self._save_and_reload()

    def delete_group(self) -> None:
        if self.current_group in {ALL_GROUP_LABEL, ""}:
            QMessageBox.information(self, "グループ削除", "削除したいグループタブを選択してください。")
            return
        target_groups = [group for group in self._group_names() if group not in {ALL_GROUP_LABEL, self.current_group}]
        if DEFAULT_GROUP_LABEL not in target_groups:
            target_groups.append(DEFAULT_GROUP_LABEL)
        target_group, accepted = QInputDialog.getItem(
            self,
            "グループ削除",
            f"'{self.current_group}' の項目を移動する先グループ",
            target_groups,
            0,
            False,
        )
        if not accepted:
            return
        destination = target_group or DEFAULT_GROUP_LABEL
        for item in self.config.items:
            if (item.group or DEFAULT_GROUP_LABEL) == self.current_group:
                item.group = destination
        self.config.group_order = [group for group in self.config.group_order if group != self.current_group]
        if destination not in self.config.group_order:
            self.config.group_order.append(destination)
        self.current_group = destination
        self._save_and_reload()

    def move_group(self, direction: int) -> None:
        if self.current_group in {ALL_GROUP_LABEL, ""}:
            QMessageBox.information(self, "グループ移動", "移動したいグループタブを選択してください。")
            return
        groups = list(self.config.group_order)
        if self.current_group not in groups:
            return
        index = groups.index(self.current_group)
        new_index = index + direction
        if new_index < 0 or new_index >= len(groups):
            return
        groups[index], groups[new_index] = groups[new_index], groups[index]
        self.config.group_order = groups
        self._save_and_reload()

    def add_item(self) -> None:
        dialog = ItemEditor(self, groups=self._group_names(), default_group=self._editor_default_group())
        if dialog.exec() != QDialog.Accepted:
            return
        item = dialog.build_item(self.config_manager.next_item_id(self.config))
        if not item.name or not item.command_name or not item.target:
            QMessageBox.warning(self, "Invalid item", "表示名、コマンド名、実行内容は必須です。")
            return
        self.config.items.append(item)
        if item.group not in self.config.group_order:
            self.config.group_order.append(item.group)
        self.current_group = item.group
        self._save_and_reload()

    def edit_item(self) -> None:
        current = self.item_list.currentItem()
        if current is None:
            return
        item_id = current.data(Qt.UserRole)
        original = next((item for item in self.config.items if item.id == item_id), None)
        if original is None:
            return

        dialog = ItemEditor(self, deepcopy(original), groups=self._group_names(), default_group=original.group)
        if dialog.exec() != QDialog.Accepted:
            return
        updated = dialog.build_item(original.id, original.usage_count, original.last_used)
        if not updated.name or not updated.command_name or not updated.target:
            QMessageBox.warning(self, "Invalid item", "表示名、コマンド名、実行内容は必須です。")
            return
        index = self.config.items.index(original)
        self.config.items[index] = updated
        if updated.group not in self.config.group_order:
            self.config.group_order.append(updated.group)
        self.current_group = updated.group
        self._save_and_reload()

    def delete_item(self) -> None:
        selected_ids = self._selected_item_ids()
        if not selected_ids:
            return
        self.config.items = [item for item in self.config.items if item.id not in selected_ids]
        self._save_and_reload()

    def create_backup(self) -> None:
        backup_path = self.config_manager.create_backup("manual")
        if backup_path is None:
            self._save_config()
            backup_path = self.config_manager.create_backup("manual")
        if backup_path is not None:
            self._show_saved_status(f"バックアップ保存: {backup_path.name}")

    def open_import_dialog(self) -> None:
        dialog = ImportItemsDialog(self, self._group_names(), self._editor_default_group())
        if dialog.exec() != QDialog.Accepted:
            return
        discovered = dialog.selected_items()
        self._import_discovered_items(
            discovered,
            dialog.selected_group(),
            title="一括登録完了",
        )

    def restore_backup(self) -> None:
        backups = self.config_manager.list_backups()
        if not backups:
            QMessageBox.information(self, "復元", "復元できるバックアップがありません。")
            return
        choices = [path.name for path in backups]
        selected_name, accepted = QInputDialog.getItem(self, "復元", "復元するバックアップ", choices, 0, False)
        if not accepted or not selected_name:
            return
        selected_path = next((path for path in backups if path.name == selected_name), None)
        if selected_path is None:
            return
        restored = self.config_manager.restore_backup(selected_path)
        self.config.settings = restored.settings
        self.config.group_order = restored.group_order
        self.config.items = restored.items
        self.current_group = ALL_GROUP_LABEL
        self.on_saved()
        self.reload()
        self._show_saved_status(f"復元済み: {selected_name}")

    def open_log_folder(self) -> None:
        log_dir = Path(self.config_manager.base_dir) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(log_dir))  # type: ignore[attr-defined]

    def show_item_context_menu(self, position) -> None:
        clicked_item = self.item_list.itemAt(position)
        if clicked_item is not None and not clicked_item.isSelected():
            self.item_list.setCurrentItem(clicked_item)
            clicked_item.setSelected(True)

        selected_ids = self._selected_item_ids()
        menu = QMenu(self)
        edit_action = menu.addAction("編集")
        edit_action.setEnabled(len(selected_ids) == 1)
        delete_action = menu.addAction("削除")
        delete_action.setEnabled(bool(selected_ids))
        favorite_action = menu.addAction("お気に入り切替")
        favorite_action.setEnabled(bool(selected_ids))
        menu.addSeparator()
        select_all_action = menu.addAction("全選択")
        group_menu = menu.addMenu("グループ変更")
        group_menu.setEnabled(bool(selected_ids))

        for group in self._assignable_groups():
            action = group_menu.addAction(group)
            action.triggered.connect(lambda checked=False, group_name=group: self.assign_selected_items_to_group(group_name))
        group_menu.addSeparator()
        create_group_action = group_menu.addAction("新しいグループを作成して移動")
        create_group_action.triggered.connect(self.create_group_and_assign_selected_items)

        chosen_action = menu.exec(self.item_list.mapToGlobal(position))
        if chosen_action == edit_action:
            self.edit_item()
        elif chosen_action == delete_action:
            self.delete_item()
        elif chosen_action == favorite_action:
            self.toggle_favorite_selected_items()
        elif chosen_action == select_all_action:
            self.item_list.selectAll()

    def assign_selected_items_to_group(self, group_name: str) -> None:
        selected_ids = self._selected_item_ids()
        if not selected_ids:
            return
        target_group = group_name.strip() or DEFAULT_GROUP_LABEL
        for item in self.config.items:
            if item.id in selected_ids:
                item.group = target_group
        if target_group not in self.config.group_order:
            self.config.group_order.append(target_group)
        self.current_group = target_group
        self._save_and_reload()

    def create_group_and_assign_selected_items(self) -> None:
        selected_ids = self._selected_item_ids()
        if not selected_ids:
            return
        group_name, accepted = QInputDialog.getText(self, "グループ変更", "移動先の新しいグループ名")
        if not accepted:
            return
        normalized = group_name.strip()
        if not normalized:
            return
        if normalized not in self.config.group_order:
            self.config.group_order.append(normalized)
        self.assign_selected_items_to_group(normalized)

    def toggle_favorite_selected_items(self) -> None:
        selected_ids = self._selected_item_ids()
        if not selected_ids:
            return
        for item in self.config.items:
            if item.id in selected_ids:
                item.favorite = not item.favorite
        self._save_and_reload()

    def reorder_items_from_view(self) -> None:
        if self._suspend_auto_save:
            return
        scoped_items = self._items_for_current_group()
        if self.item_list.count() != len(scoped_items):
            logger.warning(
                "skip reorder in filtered view current_group=%s visible=%s scoped=%s",
                self.current_group,
                self.item_list.count(),
                len(scoped_items),
            )
            return
        visible_ids = [self.item_list.item(index).data(Qt.UserRole) for index in range(self.item_list.count())]
        if not visible_ids:
            return
        item_lookup = {item.id: item for item in self.config.items}
        visible_items = [item_lookup[item_id] for item_id in visible_ids if item_id in item_lookup]
        if self.current_group == ALL_GROUP_LABEL:
            self.config.items = visible_items + [item for item in self.config.items if item.id not in visible_ids]
        else:
            target_group = self.current_group
            ordered_items = []
            inserted = False
            for item in self.config.items:
                if (item.group or DEFAULT_GROUP_LABEL) == target_group:
                    if not inserted:
                        ordered_items.extend(visible_items)
                        inserted = True
                    continue
                ordered_items.append(item)
            if not inserted:
                ordered_items.extend(visible_items)
            self.config.items = ordered_items
        self._save_config()
        self._show_saved_status("並び順を保存")

    def keyPressEvent(self, event) -> None:
        if self.item_list.hasFocus() and event.matches(QKeySequence.StandardKey.SelectAll):
            self.item_list.selectAll()
            event.accept()
            return
        if event.key() == Qt.Key_Delete and self.item_list.hasFocus():
            self.delete_item()
            event.accept()
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event) -> None:
        mime_data = event.mimeData()
        if mime_data.hasUrls():
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event) -> None:
        paths = []
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.exists():
                paths.append(path)

        added = 0
        for path in paths:
            if self._register_dropped_path(path):
                added += 1

        if added:
            self._save_and_reload()
            QMessageBox.information(self, "登録完了", f"{added} 件を登録しました。")
            event.acceptProposedAction()
            return

        QMessageBox.warning(self, "登録失敗", "登録できるローカルファイルまたはフォルダがありませんでした。")
        event.ignore()

    def _import_discovered_items(self, discovered: list[DiscoveredItem], target_group: str, title: str = "一括登録", empty_message: str | None = None) -> None:
        if not discovered:
            QMessageBox.information(self, title, empty_message or "登録できる項目がありませんでした。")
            return

        added = 0
        skipped = 0
        existing_targets = {self._compare_target_key(item) for item in self.config.items}

        for source in discovered:
            compare_key = self._compare_discovered_target_key(source)
            if compare_key in existing_targets:
                skipped += 1
                continue

            item = LauncherItem(
                id=self.config_manager.next_item_id(self.config),
                name=source.name,
                command_name=self._make_command_name(source.name),
                aliases=[],
                type=source.type,
                target=source.target,
                args=source.args,
                workdir=source.workdir,
                description=source.description,
                group=target_group,
            )
            self.config.items.append(item)
            existing_targets.add(compare_key)
            added += 1

        if added:
            if target_group not in self.config.group_order:
                self.config.group_order.append(target_group)
            self.current_group = target_group
            self._save_and_reload()
            message = f"{added} 件を登録しました。"
            if skipped:
                message += f"\n{skipped} 件は既存登録のためスキップしました。"
            QMessageBox.information(self, title, message)
            return

        if skipped:
            QMessageBox.information(self, title, "対象はすべて登録済みでした。")
            return

        QMessageBox.information(self, title, empty_message or "登録できる項目がありませんでした。")

    def _register_dropped_path(self, path: Path) -> bool:
        item_type = self._detect_item_type(path)
        if item_type is None:
            return False

        target_group = self._editor_default_group()
        command_name = self._make_command_name(path.stem or path.name)
        item = LauncherItem(
            id=self.config_manager.next_item_id(self.config),
            name=path.stem or path.name,
            command_name=command_name,
            aliases=[],
            type=item_type,
            target=str(path),
            workdir=str(path.parent) if path.is_file() else str(path),
            description=self._build_description(path, item_type),
            group=target_group,
        )
        self.config.items.append(item)
        if target_group not in self.config.group_order:
            self.config.group_order.append(target_group)
        self.current_group = target_group
        return True

    def _compare_target_key(self, item: LauncherItem) -> str:
        if item.type == "url":
            args = re.sub(r"\s+", " ", item.args.strip().lower())
            return f"url:{item.target.strip().lower()}|args:{args}"
        args = re.sub(r"\s+", " ", item.args.strip().lower())
        candidate = item.target.strip()
        if self._looks_like_path(candidate):
            path = Path(candidate).expanduser()
            return f"path:{path.resolve(strict=False)}|args:{args}"
        return f"text:{candidate.lower()}|args:{args}"

    def _compare_discovered_target_key(self, source: DiscoveredItem) -> str:
        args = re.sub(r"\s+", " ", source.args.strip().lower())
        if source.type == "url":
            return f"url:{source.target.strip().lower()}|args:{args}"
        path = Path(source.target).expanduser()
        return f"path:{path.resolve(strict=False)}|args:{args}"

    def _looks_like_path(self, value: str) -> bool:
        normalized = value.strip().strip('"')
        return bool(
            normalized.startswith(("~", ".", r"\\"))
            or ":" in normalized
            or "\\" in normalized
            or "/" in normalized
        )

    def _detect_item_type(self, path: Path) -> str | None:
        if path.is_dir():
            return "file"
        suffix = path.suffix.lower()
        if suffix == ".ps1":
            return "ps"
        if suffix in {".exe", ".lnk", ".bat", ".cmd"}:
            return "app"
        if path.is_file():
            return "file"
        return None

    def _make_command_name(self, raw_name: str) -> str:
        base = re.sub(r"[^a-zA-Z0-9]+", "_", raw_name.strip().lower()).strip("_") or "item"
        existing = {item.command_name.lower() for item in self.config.items}
        candidate = base
        index = 2
        while candidate.lower() in existing:
            candidate = f"{base}_{index}"
            index += 1
        return candidate

    def _build_description(self, path: Path, item_type: str) -> str:
        if path.is_dir():
            return f"フォルダを開く: {path.name}"
        if item_type == "ps":
            return f"PowerShell スクリプトを実行: {path.name}"
        if item_type == "app":
            return f"アプリを起動: {path.name}"
        return f"ファイルを開く: {path.name}"

    def _apply_settings_inputs(self) -> None:
        self.config.settings.hotkey = self.hotkey_edit.text().strip()
        self.config.settings.alt_double_tap = self.alt_double_tap_check.isChecked()
        self.config.settings.launch_on_startup = self.startup_check.isChecked()

    def _save_config(self) -> None:
        self._apply_settings_inputs()
        self.config_manager.save(self.config)
        self.on_saved()
        self._show_saved_status()

    def _save_and_reload(self) -> None:
        self._save_config()
        self.reload()

    def _show_saved_status(self, text: str = "保存済み") -> None:
        self.save_status_label.setText(text)
        QTimer.singleShot(1500, lambda: self.save_status_label.setText(""))

    def _selected_item_ids(self) -> set[str]:
        return {item.data(Qt.UserRole) for item in self.item_list.selectedItems()}

    def _assignable_groups(self) -> list[str]:
        return [group for group in self._group_names() if group != ALL_GROUP_LABEL]

    def _group_names(self) -> list[str]:
        self.config_manager.normalize_group_order(self.config)
        groups = list(self.config.group_order)
        if self.current_group not in groups and self.current_group != ALL_GROUP_LABEL:
            groups.append(self.current_group)
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

    def _editor_default_group(self) -> str:
        return DEFAULT_GROUP_LABEL if self.current_group == ALL_GROUP_LABEL else self.current_group

    def _dedupe_group_order(self) -> None:
        ordered = []
        for group in self.config.group_order:
            if group not in ordered:
                ordered.append(group)
        self.config.group_order = ordered

    def _on_group_changed(self, index: int) -> None:
        if index < 0:
            return
        self.current_group = self.group_tabs.tabText(index)
        self.reload()

    def auto_save_settings(self) -> None:
        if self._suspend_auto_save:
            return
        self._save_config()
        self.reload()

    def save_settings(self) -> None:
        self._save_config()
        QMessageBox.information(self, "Saved", "設定を保存しました。")
