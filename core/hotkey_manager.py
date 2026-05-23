from __future__ import annotations

import ctypes
import logging
import time
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QTimer


logger = logging.getLogger(__name__)

WM_HOTKEY = 0x0312
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WH_KEYBOARD_LL = 13
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
HOTKEY_ID = 1
VK_MENU = 0x12
VK_LMENU = 0xA4
VK_RMENU = 0xA5
ALT_DOUBLE_TAP_WINDOW = 0.4

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
LRESULT = wintypes.LPARAM

user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt_x", ctypes.c_long),
        ("pt_y", ctypes.c_long),
        ("lPrivate", wintypes.DWORD),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


LowLevelKeyboardProc = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class HotkeyManager(QObject, QAbstractNativeEventFilter):
    def __init__(self, app, hotkey: str, alt_double_tap: bool, callback) -> None:
        super().__init__()
        self.app = app
        self.hotkey = hotkey
        self.alt_double_tap = alt_double_tap
        self.callback = callback
        self.registered = False
        self.keyboard_hook = None
        self.last_error = ""
        self._keyboard_proc_ref = LowLevelKeyboardProc(self._low_level_keyboard_proc)
        self._alt_pressed = False
        self._alt_tap_candidate = False
        self._last_alt_tap = 0.0

    def start(self) -> bool:
        self.app.installNativeEventFilter(self)
        self.app.aboutToQuit.connect(self.stop)
        return self.update_settings(self.hotkey, self.alt_double_tap)

    def stop(self) -> None:
        if self.registered:
            user32.UnregisterHotKey(None, HOTKEY_ID)
            self.registered = False
        if self.keyboard_hook:
            user32.UnhookWindowsHookEx(self.keyboard_hook)
            self.keyboard_hook = None

    def update_settings(self, hotkey: str, alt_double_tap: bool) -> bool:
        self.hotkey = hotkey.strip()
        self.alt_double_tap = alt_double_tap
        self.stop()

        errors: list[str] = []
        active = False

        if self.hotkey:
            if self._register_hotkey(self.hotkey):
                active = True
            else:
                errors.append(self.last_error)

        if self.alt_double_tap:
            if self._install_keyboard_hook():
                active = True
            else:
                errors.append("Alt 2回押しの監視開始に失敗しました。")

        if not active and not errors:
            errors.append("ホットキーか Alt 2回押しのどちらかを有効にしてください。")

        self.last_error = " / ".join(part for part in errors if part)
        return active

    def nativeEventFilter(self, event_type, message):
        if event_type not in {b"windows_generic_MSG", b"windows_dispatcher_MSG", "windows_generic_MSG", "windows_dispatcher_MSG"}:
            return False, 0

        msg = ctypes.cast(message, ctypes.POINTER(MSG)).contents
        if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
            QTimer.singleShot(0, self.callback)
            return True, 0
        return False, 0

    def _register_hotkey(self, hotkey: str) -> bool:
        try:
            modifiers, vk = self._parse_hotkey(hotkey)
        except ValueError as exc:
            self.last_error = str(exc)
            return False

        if not user32.RegisterHotKey(None, HOTKEY_ID, modifiers, vk):
            self.last_error = f"RegisterHotKey failed: {ctypes.GetLastError()}"
            logger.warning("hotkey registration failed for %s: %s", hotkey, self.last_error)
            return False

        self.registered = True
        logger.info("hotkey registration succeeded for %s", hotkey)
        return True

    def _install_keyboard_hook(self) -> bool:
        module_handle = kernel32.GetModuleHandleW(None)
        self.keyboard_hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            self._keyboard_proc_ref,
            module_handle,
            0,
        )
        if not self.keyboard_hook:
            logger.warning("failed to install low-level keyboard hook")
            return False
        logger.info("alt double-tap hook enabled")
        return True

    def _low_level_keyboard_proc(self, n_code, w_param, l_param):
        if n_code >= 0 and self.alt_double_tap:
            key = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents.vkCode
            if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                self._handle_keydown(key)
            elif w_param in (WM_KEYUP, WM_SYSKEYUP):
                self._handle_keyup(key)
        return user32.CallNextHookEx(self.keyboard_hook, n_code, w_param, l_param)

    def _handle_keydown(self, key: int) -> None:
        if key in (VK_MENU, VK_LMENU, VK_RMENU):
            if not self._alt_pressed:
                self._alt_pressed = True
                self._alt_tap_candidate = True
            return

        if self._alt_pressed:
            self._alt_tap_candidate = False

    def _handle_keyup(self, key: int) -> None:
        if key not in (VK_MENU, VK_LMENU, VK_RMENU):
            if self._alt_pressed:
                self._alt_tap_candidate = False
            return

        if not self._alt_pressed:
            return

        self._alt_pressed = False
        if not self._alt_tap_candidate:
            return

        now = time.monotonic()
        if now - self._last_alt_tap <= ALT_DOUBLE_TAP_WINDOW:
            self._last_alt_tap = 0.0
            QTimer.singleShot(0, self.callback)
            logger.info("alt double-tap detected")
        else:
            self._last_alt_tap = now

    def _parse_hotkey(self, hotkey: str) -> tuple[int, int]:
        parts = [part.strip() for part in hotkey.split("+") if part.strip()]
        if len(parts) < 2:
            raise ValueError("ホットキーは 'Ctrl+Space' の形式で指定してください。")

        modifiers = 0
        key_name = None
        for part in parts:
            lowered = part.lower()
            if lowered in {"ctrl", "control"}:
                modifiers |= MOD_CONTROL
            elif lowered == "alt":
                modifiers |= MOD_ALT
            elif lowered == "shift":
                modifiers |= MOD_SHIFT
            elif lowered in {"win", "meta", "super"}:
                modifiers |= MOD_WIN
            else:
                key_name = part

        if modifiers == 0 or key_name is None:
            raise ValueError("修飾キーと通常キーの両方が必要です。")

        vk = self._parse_vk(key_name)
        return modifiers, vk

    def _parse_vk(self, key_name: str) -> int:
        upper = key_name.upper()
        special = {
            "SPACE": 0x20,
            "TAB": 0x09,
            "ENTER": 0x0D,
            "ESC": 0x1B,
            "ESCAPE": 0x1B,
            "UP": 0x26,
            "DOWN": 0x28,
            "LEFT": 0x25,
            "RIGHT": 0x27,
        }
        if upper in special:
            return special[upper]
        if len(upper) == 1 and upper.isalnum():
            return ord(upper)
        if upper.startswith("F") and upper[1:].isdigit():
            value = int(upper[1:])
            if 1 <= value <= 24:
                return 0x6F + value
        raise ValueError(f"未対応のキーです: {key_name}")
