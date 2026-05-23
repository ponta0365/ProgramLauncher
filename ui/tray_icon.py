from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon


class LauncherTrayIcon(QSystemTrayIcon):
    def __init__(self, launcher, settings, app: QApplication) -> None:
        icon = app.style().standardIcon(QStyle.SP_ComputerIcon)
        super().__init__(icon)
        self.launcher = launcher
        self.settings = settings
        self.app = app

        self.setToolTip("Program Launcher")
        menu = QMenu()

        open_action = QAction("プログラム選択を開く", self)
        open_action.triggered.connect(self.launcher.show_launcher)
        menu.addAction(open_action)

        settings_action = QAction("設定を開く", self)
        settings_action.triggered.connect(self.launcher.open_settings)
        menu.addAction(settings_action)

        quit_action = QAction("終了", self)
        quit_action.triggered.connect(self.app.quit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self.launcher.show_launcher()
