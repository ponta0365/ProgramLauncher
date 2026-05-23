from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from core.config_manager import ConfigManager
from core.executor import Executor
from core.hotkey_manager import HotkeyManager
from core.logging_setup import configure_logging, install_exception_hook
from core.runtime_paths import get_app_base_dir
from core.search_engine import SearchEngine
from core.single_instance import SingleInstanceGuard
from core.startup_manager import StartupManager
from ui.launcher_window import LauncherWindow
from ui.settings_window import SettingsWindow
from ui.tray_icon import LauncherTrayIcon


logger = logging.getLogger(__name__)


def run() -> int:
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("Program Launcher")
    qt_app.setQuitOnLastWindowClosed(False)

    instance_guard = SingleInstanceGuard("Local\\ProgramLauncherSingleton")
    if not instance_guard.acquire():
        instance_guard.signal_existing_instance()
        QMessageBox.information(None, "Already Running", "Program Launcher はすでに起動しています。既存の画面を前面表示します。")
        return 0
    qt_app.aboutToQuit.connect(instance_guard.release)

    base_dir = get_app_base_dir()
    log_path = configure_logging(base_dir)
    install_exception_hook()
    logger.info("application boot")

    config_manager = ConfigManager(base_dir)
    config = config_manager.load()
    logger.info("config loaded from %s", config_manager.config_path)

    startup_manager = StartupManager(base_dir)
    startup_manager.apply(config.settings.launch_on_startup)

    search_engine = SearchEngine()
    executor = Executor()

    launcher = LauncherWindow(config_manager, search_engine, executor, config)
    instance_guard.set_activate_callback(launcher.show_launcher)
    hotkey = HotkeyManager(qt_app, config.settings.hotkey, config.settings.alt_double_tap, launcher.show_launcher)
    launcher.hotkey_manager = hotkey

    def on_saved() -> None:
        config_manager.normalize_group_order(config)
        launcher.refresh_items()
        logger.info("settings saved")
        startup_manager.apply(config.settings.launch_on_startup)
        if not hotkey.update_settings(config.settings.hotkey, config.settings.alt_double_tap):
            logger.warning("launch trigger update failed: %s", hotkey.last_error)
            QMessageBox.warning(None, "Launch trigger update failed", hotkey.last_error or "起動トリガー更新に失敗しました。")
            launcher.show_launcher()

    settings = SettingsWindow(config_manager, config, on_saved)
    launcher.set_settings_window(settings)

    if not hotkey.start():
        logger.warning("launch trigger start failed: %s", hotkey.last_error)
        QMessageBox.warning(None, "Launch trigger unavailable", hotkey.last_error or "起動トリガー登録に失敗しました。")
        launcher.show_launcher()
    else:
        logger.info(
            "launch trigger active: hotkey=%s alt_double_tap=%s",
            config.settings.hotkey,
            config.settings.alt_double_tap,
        )

    tray = LauncherTrayIcon(launcher, settings, qt_app)
    launcher.tray_icon = tray

    if not QSystemTrayIcon.isSystemTrayAvailable():
        logger.warning("system tray unavailable")
        QMessageBox.warning(
            None,
            "Tray unavailable",
            "システムトレイが利用できないため、プログラム選択画面を表示した状態で動作します。",
        )
        launcher.show_launcher()
    else:
        tray.show()
        logger.info("tray icon shown")

    logger.info("startup complete; log file=%s", log_path)
    return qt_app.exec()
