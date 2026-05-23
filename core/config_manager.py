from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from core.models import LauncherConfig, LauncherItem, LauncherSettings


DEFAULT_GROUP = "未分類"
POWERSHELL_SWITCH_PREFIXES = ("-executionpolicy", "-file", "-noprofile", "-command", "-windowstyle")
MAX_BACKUPS = 30


class ConfigManager:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.data_dir = base_dir / "data"
        self.backup_dir = self.data_dir / "backups"
        self.config_path = self.data_dir / "launcher_config.json"

    def load(self) -> LauncherConfig:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists():
            config = self._default_config()
            self.save(config)
            return config

        raw = json.loads(self.config_path.read_text(encoding="utf-8-sig"))
        settings = LauncherSettings(**raw.get("settings", {}))
        items = [LauncherItem(**item) for item in raw.get("items", [])]
        group_order = list(raw.get("group_order", []))
        config = LauncherConfig(version=raw.get("version", "2.0"), settings=settings, group_order=group_order, items=items)
        self.normalize_group_order(config)
        self.normalize_items(config)
        return config

    def save(self, config: LauncherConfig) -> None:
        self.normalize_group_order(config)
        self.normalize_items(config)
        if self.config_path.exists():
            self.create_backup()
        payload = asdict(config)
        self.config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def create_backup(self, label: str = "backup") -> Path | None:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists():
            return None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_label = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in label).strip("_") or "backup"
        backup_name = f"{timestamp}_{safe_label}_{uuid4().hex[:6]}.json"
        backup_path = self.backup_dir / backup_name
        shutil.copy2(self.config_path, backup_path)
        self._prune_backups()
        return backup_path

    def list_backups(self) -> list[Path]:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        return sorted(self.backup_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)

    def restore_backup(self, backup_path: Path) -> LauncherConfig:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        if not backup_path.exists():
            raise FileNotFoundError(str(backup_path))
        if self.config_path.exists():
            self.create_backup("before_restore")
        shutil.copy2(backup_path, self.config_path)
        return self.load()

    def next_item_id(self, config: LauncherConfig) -> str:
        existing = {item.id for item in config.items}
        index = 1
        while True:
            candidate = f"item_{index:03d}"
            if candidate not in existing:
                return candidate
            index += 1

    def normalize_group_order(self, config: LauncherConfig) -> None:
        item_groups = []
        for item in config.items:
            group = (item.group or DEFAULT_GROUP).strip() or DEFAULT_GROUP
            item.group = group
            if group not in item_groups:
                item_groups.append(group)

        merged = []
        for group in config.group_order:
            normalized = (group or DEFAULT_GROUP).strip() or DEFAULT_GROUP
            if normalized not in merged:
                merged.append(normalized)
        for group in item_groups:
            if group not in merged:
                merged.append(group)
        if not merged:
            merged.append(DEFAULT_GROUP)
        config.group_order = merged

    def normalize_items(self, config: LauncherConfig) -> None:
        for item in config.items:
            item.target = self._normalize_item_target(item)
            if item.type == "ps" and item.description.startswith("ファイルを開く:"):
                item.description = f"PowerShell スクリプトを実行: {Path(item.target).name}"

    def _normalize_item_target(self, item: LauncherItem) -> str:
        target = item.target.strip()
        if item.type != "ps" or not target:
            return target

        lowered = target.lower()
        if lowered.startswith(("powershell", "powershell.exe", "pwsh", "pwsh.exe")):
            return target
        if lowered.startswith(POWERSHELL_SWITCH_PREFIXES):
            return f"powershell {target}"
        return target

    def _prune_backups(self) -> None:
        backups = self.list_backups()
        for path in backups[MAX_BACKUPS:]:
            path.unlink(missing_ok=True)

    def _default_config(self) -> LauncherConfig:
        config = LauncherConfig(
            items=[
                LauncherItem(
                    id="item_001",
                    name="Windows Terminal",
                    command_name="wt",
                    aliases=["terminal"],
                    type="app",
                    target="wt.exe",
                    description="Windows Terminal を起動",
                ),
                LauncherItem(
                    id="item_002",
                    name="Google",
                    command_name="google",
                    aliases=["search"],
                    type="url",
                    target="https://www.google.com",
                    description="ブラウザで Google を開く",
                ),
            ]
        )
        self.normalize_group_order(config)
        self.normalize_items(config)
        return config
