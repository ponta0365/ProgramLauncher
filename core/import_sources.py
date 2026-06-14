from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


try:
    import winreg  # type: ignore
except ImportError:  # pragma: no cover - non-Windows fallback
    winreg = None  # type: ignore


@dataclass(frozen=True)
class DiscoveredItem:
    name: str
    type: str
    target: str
    workdir: str
    description: str


WINDOWS_UNINSTALL_KEYS = []
if winreg is not None:
    WINDOWS_UNINSTALL_KEYS = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
STEAM_APPMANIFEST_PATTERN = re.compile(r'^"appid"\s*"(?P<appid>\d+)"|^"name"\s*"(?P<name>[^"]+)"|^"installdir"\s*"(?P<installdir>[^"]+)"', re.IGNORECASE)
WINDOWS_PATH_PATTERN = re.compile(
    r'(?i)([A-Za-z]:\\(?:[^<>:"/\\|?*\r\n]+\\)*[^<>:"/\\|?*\r\n]+\.(?:exe|lnk|bat|cmd))'
)


def discover_windows_apps() -> list[DiscoveredItem]:
    if winreg is None:
        return []

    discovered: list[DiscoveredItem] = []
    seen_targets: set[str] = set()

    for hive, subkey in WINDOWS_UNINSTALL_KEYS:
        try:
            with winreg.OpenKey(hive, subkey) as root:
                for index in range(winreg.QueryInfoKey(root)[0]):
                    try:
                        key_name = winreg.EnumKey(root, index)
                        with winreg.OpenKey(root, key_name) as app_key:
                            item = _discover_windows_app_from_key(app_key)
                    except OSError:
                        continue
                    if item is None:
                        continue
                    normalized = _normalize_compare_target(item.target)
                    if normalized in seen_targets:
                        continue
                    seen_targets.add(normalized)
                    discovered.append(item)
        except OSError:
            continue

    discovered.sort(key=lambda item: item.name.lower())
    return discovered


def discover_steam_games() -> list[DiscoveredItem]:
    steam_root = _detect_steam_root()
    if steam_root is None:
        return []

    library_paths = _discover_steam_libraries(steam_root)
    manifests: list[Path] = []
    for library in library_paths:
        steamapps = library / "steamapps"
        if not steamapps.exists():
            continue
        manifests.extend(sorted(steamapps.glob("appmanifest_*.acf")))

    discovered: list[DiscoveredItem] = []
    seen_appids: set[str] = set()

    for manifest in manifests:
        parsed = _parse_steam_manifest(manifest)
        if parsed is None:
            continue
        appid, name = parsed
        if appid in seen_appids:
            continue
        seen_appids.add(appid)
        discovered.append(
            DiscoveredItem(
                name=name,
                type="url",
                target=f"steam://rungameid/{appid}",
                workdir="",
                description=f"Steam ゲームを起動: {name}",
            )
        )

    discovered.sort(key=lambda item: item.name.lower())
    return discovered


def discover_files_in_folder(folder: Path, extensions: list[str], recursive: bool) -> list[DiscoveredItem]:
    paths = []
    for extension in extensions:
        pattern = f"*{extension}"
        matched = folder.rglob(pattern) if recursive else folder.glob(pattern)
        paths.extend(path for path in matched if path.is_file())

    unique_paths = sorted({path.resolve(strict=False): path for path in paths}.values(), key=lambda path: str(path).lower())
    discovered: list[DiscoveredItem] = []

    for file_path in unique_paths:
        item_type = _detect_file_item_type(file_path)
        if item_type is None:
            continue
        discovered.append(
            DiscoveredItem(
                name=file_path.stem or file_path.name,
                type=item_type,
                target=str(file_path),
                workdir=str(file_path.parent),
                description=_build_file_description(file_path, item_type),
            )
        )

    return discovered


def _discover_windows_app_from_key(app_key) -> DiscoveredItem | None:
    display_name = _read_reg_value(app_key, "DisplayName")
    if not display_name:
        return None

    if _read_reg_dword(app_key, "SystemComponent") == 1:
        return None

    target = _resolve_windows_launch_target(app_key)
    if not target:
        return None

    target_path = Path(target)
    workdir = str(target_path.parent) if target_path.parent else ""
    return DiscoveredItem(
        name=display_name,
        type="app",
        target=target,
        workdir=workdir,
        description=f"Windows アプリを起動: {display_name}",
    )


def _resolve_windows_launch_target(app_key) -> str | None:
    for value_name in ("DisplayIcon", "InstallLocation", "UninstallString", "QuietUninstallString"):
        raw = _read_reg_value(app_key, value_name)
        if not raw:
            continue
        candidate = _extract_windows_path(raw)
        if candidate and Path(candidate).exists():
            if Path(candidate).is_dir():
                exe = _find_executable_in_folder(Path(candidate))
                if exe is not None:
                    return str(exe)
                continue
            return candidate
    return None


def _find_executable_in_folder(folder: Path) -> Path | None:
    direct = sorted(folder.glob("*.exe"))
    if direct:
        return direct[0]
    nested = sorted(folder.rglob("*.exe"))
    return nested[0] if nested else None


def _detect_steam_root() -> Path | None:
    candidates: list[str] = []
    if winreg is not None:
        reg_paths = [
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam"),
        ]
        for hive, subkey in reg_paths:
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    for name in ("SteamPath", "InstallPath"):
                        value = _read_reg_value(key, name)
                        if value:
                            candidates.append(value)
            except OSError:
                continue

    candidates.extend(
        [
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)") + r"\Steam",
            os.environ.get("PROGRAMFILES", r"C:\Program Files") + r"\Steam",
        ]
    )

    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return path
    return None


def _discover_steam_libraries(steam_root: Path) -> list[Path]:
    libraries = [steam_root]
    library_vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    if not library_vdf.exists():
        return libraries

    text = library_vdf.read_text(encoding="utf-8", errors="ignore")
    for match in re.finditer(r'"path"\s*"([^"]+)"', text, re.IGNORECASE):
        raw_path = match.group(1).replace("\\\\", "\\")
        path = Path(raw_path)
        if path.exists() and path not in libraries:
            libraries.append(path)
    return libraries


def _parse_steam_manifest(manifest: Path) -> tuple[str, str] | None:
    appid = ""
    name = ""
    try:
        for line in manifest.read_text(encoding="utf-8", errors="ignore").splitlines():
            match = STEAM_APPMANIFEST_PATTERN.match(line.strip())
            if not match:
                continue
            if match.group("appid"):
                appid = match.group("appid")
            elif match.group("name"):
                name = match.group("name")
    except OSError:
        return None

    if not appid or not name:
        return None
    return appid, name


def _extract_windows_path(raw: str) -> str | None:
    value = raw.strip().strip('"')
    match = WINDOWS_PATH_PATTERN.search(value)
    if match:
        candidate = match.group(1).strip('"')
        if candidate.lower().endswith(".exe"):
            return candidate.split(",")[0].strip().strip('"')
        return candidate

    first = value.split(",", 1)[0].strip().strip('"')
    if first and Path(first).exists():
        return first
    return None


def _read_reg_value(key, name: str) -> str:
    try:
        value, _ = winreg.QueryValueEx(key, name)
    except OSError:
        return ""
    return value if isinstance(value, str) else str(value)


def _read_reg_dword(key, name: str) -> int:
    try:
        value, _ = winreg.QueryValueEx(key, name)
    except OSError:
        return 0
    return int(value) if isinstance(value, int) else 0


def _normalize_compare_target(value: str) -> str:
    return value.replace("/", "\\").strip().lower()


def _detect_file_item_type(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix == ".ps1":
        return "ps"
    if suffix in {".exe", ".lnk", ".bat", ".cmd"}:
        return "app"
    if path.is_file():
        return "file"
    return None


def _build_file_description(path: Path, item_type: str) -> str:
    if item_type == "ps":
        return f"PowerShell スクリプトを実行: {path.name}"
    if item_type == "app":
        return f"アプリを起動: {path.name}"
    return f"ファイルを開く: {path.name}"
