"""全局热键轮询线程（Win32 GetAsyncKeyState）。

设计要点：
- 不使用 `keyboard` 全局钩子（曾经是鼠标卡顿的元凶）
- 在后台线程按 30ms 轮询 `GetAsyncKeyState`
- 通过 Qt 信号把 add/sub/start/pause/lock 事件派发到主线程
- 每个动作自带 400ms 去抖
"""

from __future__ import annotations

import ctypes
import sys
import time
from typing import Callable, Dict, List, Optional

from PyQt6.QtCore import QThread, pyqtSignal


_VK_MAP: Dict[str, int] = {
    "ctrl": 0x11, "control": 0x11, "left ctrl": 0x11, "right ctrl": 0x11,
    "shift": 0x10, "left shift": 0x10, "right shift": 0x10,
    "alt": 0x12, "menu": 0x12, "left alt": 0x12, "right alt": 0x12,
    "tab": 0x09, "enter": 0x0D, "return": 0x0D,
    "esc": 0x1B, "escape": 0x1B, "space": 0x20,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E,
    "insert": 0x2D, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "=": 0xBB, "+": 0xBB, "-": 0xBD, ",": 0xBC, ".": 0xBE,
    "/": 0xBF, "\\": 0xDC, "[": 0xDB, "]": 0xDD,
    ";": 0xBA, "'": 0xDE, "`": 0xC0,
    "numlock": 0x90, "capslock": 0x14, "scrolllock": 0x91,
}
for _i in range(10):
    _VK_MAP[str(_i)] = 0x30 + _i
for _i in range(26):
    _VK_MAP[chr(0x61 + _i)] = 0x41 + _i


def normalize_hotkey(value: str) -> str:
    return (value or "").strip().lower().replace(" ", "")


def parse_hotkey_to_vks(hotkey: str) -> Optional[List[int]]:
    if not hotkey:
        return None
    vks: List[int] = []
    for part in hotkey.lower().replace(" ", "").split("+"):
        vk = _VK_MAP.get(part)
        if vk is None:
            return None
        vks.append(vk)
    return vks


def is_pressed(vks: List[int]) -> bool:
    if not vks or sys.platform != "win32":
        return False
    user32 = ctypes.windll.user32
    for vk in vks:
        if not (user32.GetAsyncKeyState(vk) & 0x8000):
            return False
    return True


class HotkeyThread(QThread):
    """后台热键轮询。通过 `hotkey_triggered(action)` 信号通知主线程。"""

    ACTIONS = ("add", "sub", "start", "pause", "lock")

    hotkey_triggered = pyqtSignal(str)  # action name

    def __init__(self, hotkeys_getter: Callable[[], Dict[str, str]], parent=None):
        super().__init__(parent)
        self._get_hotkeys = hotkeys_getter
        self._stop_flag = False
        self._debounce_s = 0.4

    def request_stop(self) -> None:
        self._stop_flag = True

    def run(self) -> None:
        vk_cache: Dict[str, Optional[List[int]]] = {}
        prev_state: Dict[str, bool] = {a: False for a in self.ACTIONS}
        last_fire: Dict[str, float] = {a: 0.0 for a in self.ACTIONS}
        while not self._stop_flag:
            try:
                hk = dict(self._get_hotkeys() or {})
                for action in self.ACTIONS:
                    key = normalize_hotkey(hk.get(action, ""))
                    if not key:
                        prev_state[action] = False
                        continue
                    if key not in vk_cache:
                        vk_cache[key] = parse_hotkey_to_vks(key)
                    vks = vk_cache.get(key)
                    pressed = is_pressed(vks) if vks else False
                    if pressed and not prev_state[action]:
                        now = time.monotonic()
                        if now - last_fire[action] >= self._debounce_s:
                            last_fire[action] = now
                            self.hotkey_triggered.emit(action)
                    prev_state[action] = pressed
                time.sleep(0.03)
            except Exception:
                time.sleep(0.1)
