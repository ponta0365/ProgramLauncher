from __future__ import annotations

import sys
from pathlib import Path


def get_app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_launch_target() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return get_app_base_dir() / "main.py"


def get_runtime_executable() -> Path:
    runtime = Path(sys.executable).resolve()
    if runtime.name.lower() == "python.exe":
        pythonw = runtime.with_name("pythonw.exe")
        if pythonw.exists():
            return pythonw
    return runtime
