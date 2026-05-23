from __future__ import annotations

import ctypes
import logging
import os
import shlex
import subprocess
from pathlib import Path
from typing import Callable

from core.models import LauncherItem


ShellExecuteW = ctypes.windll.shell32.ShellExecuteW
logger = logging.getLogger(__name__)
POWERSHELL_SWITCH_PREFIXES = ("-executionpolicy", "-file", "-noprofile", "-command", "-windowstyle")


class Executor:
    def run_item(self, item: LauncherItem) -> None:
        target = os.path.expandvars(item.target)
        workdir = os.path.expandvars(item.workdir) if item.workdir else None
        logger.info("run item id=%s type=%s target=%s admin=%s", item.id, item.type, target, item.run_as_admin)

        if item.type == "app":
            target_path = Path(target)
            suffix = target_path.suffix.lower()
            if suffix == ".lnk":
                if item.run_as_admin:
                    self._run_elevated(target, [], workdir)
                else:
                    os.startfile(target)  # type: ignore[attr-defined]
                return

            args = self._split_windows_args(item.args)
            if suffix in {".bat", ".cmd"} and not item.run_as_admin:
                cmd_args = ["/c", target, *args]
                subprocess.Popen(["cmd.exe", *cmd_args], cwd=workdir or None)
                return

            if item.run_as_admin:
                self._run_elevated(target, args, workdir)
            else:
                subprocess.Popen([target, *args], cwd=workdir or None)
            return

        if item.type == "ps":
            program, args = self._build_powershell_invocation(target, workdir)
            if item.run_as_admin:
                self._run_elevated(program, args, workdir)
            else:
                subprocess.Popen([program, *args], cwd=workdir or None)
            return

        if item.type == "file":
            if item.run_as_admin:
                self._run_elevated(target, [], workdir)
            else:
                os.startfile(target)  # type: ignore[attr-defined]
            return

        if item.type == "url":
            os.startfile(target)  # type: ignore[attr-defined]
            return

        raise ValueError(f"Unsupported item type: {item.type}")

    def run_command_text(self, text: str, find_exact: Callable[[str], LauncherItem | None]) -> bool:
        candidate = find_exact(text)
        if candidate is not None:
            self.run_item(candidate)
            return True

        if text.lower().startswith("ps "):
            logger.info("run ad-hoc powershell command")
            program, args = self._build_powershell_invocation(text[3:].strip(), None)
            subprocess.Popen([program, *args])
            return True

        path = Path(os.path.expandvars(text)).expanduser()
        if path.exists():
            logger.info("open existing path %s", path)
            os.startfile(str(path))  # type: ignore[attr-defined]
            return True

        logger.info("input not executable: %s", text)
        return False

    def _build_powershell_invocation(self, target: str, workdir: str | None) -> tuple[str, list[str]]:
        stripped = target.strip()
        if not stripped:
            raise RuntimeError("PowerShell 実行内容が空です。")

        if self._looks_like_script_path(stripped):
            expanded_path = self._resolve_path(stripped.strip('"'), workdir)
            return self._build_script_invocation(expanded_path)

        parts = shlex.split(stripped, posix=False)
        if parts:
            first = parts[0].lower().strip('"')
            if first in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
                program = parts[0]
                args = self._normalize_powershell_args(parts[1:], workdir)
                return program, args
            if first.startswith(POWERSHELL_SWITCH_PREFIXES):
                return "powershell.exe", self._normalize_powershell_args(parts, workdir)

        command = stripped
        if workdir:
            command = f"Set-Location -LiteralPath '{self._escape_single_quotes(workdir)}'; {command}"
        return (
            "powershell.exe",
            [
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
        )

    def _normalize_powershell_args(self, args: list[str], workdir: str | None) -> list[str]:
        normalized: list[str] = []
        i = 0
        while i < len(args):
            arg = args[i]
            lowered = arg.lower()
            normalized.append(arg)

            if lowered == "-file" and i + 1 < len(args):
                script_path = self._resolve_path(self._strip_outer_quotes(args[i + 1]), workdir)
                normalized.append(str(script_path))
                i += 2
                continue

            if lowered == "-command" and i + 1 < len(args):
                command = args[i + 1]
                if workdir:
                    command = f"Set-Location -LiteralPath '{self._escape_single_quotes(workdir)}'; {command}"
                normalized.append(command)
                i += 2
                continue

            i += 1

        lower_args = [arg.lower() for arg in args]
        if workdir and "-command" not in lower_args and "-file" not in lower_args:
            normalized.extend(["-Command", f"Set-Location -LiteralPath '{self._escape_single_quotes(workdir)}'"])
        return normalized

    def _build_script_invocation(self, script_path: Path) -> tuple[str, list[str]]:
        return (
            "powershell.exe",
            [
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
            ],
        )

    def _resolve_path(self, raw_path: str, workdir: str | None) -> Path:
        candidate = Path(os.path.expandvars(raw_path)).expanduser()
        if candidate.is_absolute():
            return candidate
        if workdir:
            return (Path(workdir) / candidate).resolve()
        return candidate.resolve()

    def _split_windows_args(self, raw_args: str) -> list[str]:
        if not raw_args:
            return []
        return [self._strip_outer_quotes(arg) for arg in shlex.split(raw_args, posix=False)]

    def _looks_like_script_path(self, value: str) -> bool:
        stripped = value.strip().strip('"')
        lowered = stripped.lower()
        if lowered.startswith(("powershell", "powershell.exe", "pwsh", "pwsh.exe")):
            return False
        if any(flag in lowered for flag in ("-file", "-command", "-noprofile", "-executionpolicy", "-windowstyle")):
            return False
        if not lowered.endswith(".ps1"):
            return False
        return bool(
            "\\" in stripped
            or "/" in stripped
            or stripped.startswith(".")
            or stripped.startswith("~")
            or " " not in stripped
            or stripped[:2].endswith(":")
        )

    def _escape_single_quotes(self, value: str) -> str:
        return value.replace("'", "''")

    def _strip_outer_quotes(self, value: str) -> str:
        stripped = value.strip()
        if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}:
            return stripped[1:-1]
        return stripped

    def _run_elevated(self, program: str, args: list[str], workdir: str | None) -> None:
        params = subprocess.list2cmdline(args) if args else ""
        result = ShellExecuteW(None, "runas", program, params, workdir, 1)
        if result <= 32:
            logger.error("elevated launch failed program=%s result=%s", program, result)
            raise RuntimeError(f"管理者実行に失敗しました: {result}")
