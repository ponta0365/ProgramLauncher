from __future__ import annotations

import logging
from pathlib import Path

from core.runtime_paths import get_launch_target, get_runtime_executable

logger = logging.getLogger(__name__)


class StartupManager:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.startup_dir = Path.home() / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup"
        self.script_path = self.startup_dir / "ProgramLauncher.cmd"

    def apply(self, enabled: bool) -> None:
        self.startup_dir.mkdir(parents=True, exist_ok=True)
        if enabled:
            self.script_path.write_text(self._build_script(), encoding="cp932")
            logger.info("startup entry created: %s", self.script_path)
        else:
            if self.script_path.exists():
                self.script_path.unlink()
                logger.info("startup entry removed: %s", self.script_path)

    def is_enabled(self) -> bool:
        return self.script_path.exists()

    def _build_script(self) -> str:
        runtime = get_runtime_executable()
        target = get_launch_target()

        if target == runtime:
            command = f'"{runtime}"'
        else:
            command = f'"{runtime}" "{target}"'

        return (
            "@echo off\r\n"
            "setlocal\r\n"
            "timeout /t 5 /nobreak >nul\r\n"
            f"cd /d \"{self.base_dir}\"\r\n"
            f"start \"\" {command}\r\n"
        )
