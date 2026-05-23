from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class LauncherSettings:
    hotkey: str = "Ctrl+Space"
    launch_on_startup: bool = False
    alt_double_tap: bool = False


@dataclass
class LauncherItem:
    id: str
    name: str
    command_name: str
    aliases: list[str]
    type: str
    target: str
    args: str = ""
    workdir: str = ""
    description: str = ""
    group: str = "未分類"
    run_as_admin: bool = False
    usage_count: int = 0
    last_used: str = ""

    def touch(self) -> None:
        self.usage_count += 1
        self.last_used = datetime.now().isoformat(timespec="seconds")


@dataclass
class LauncherConfig:
    version: str = "2.0"
    settings: LauncherSettings = field(default_factory=LauncherSettings)
    group_order: list[str] = field(default_factory=list)
    items: list[LauncherItem] = field(default_factory=list)
