"""识别游戏窗口并把识别区域自动对齐到客户区。

公开函数：
* :func:`find_game_window` ——在当前桌面上查找洛克王国游戏窗口，返回客户区信息；
* :func:`apply_game_window` ——把查到的窗口信息应用到 ``cfg``：
    - 按客户区尺寸套用分辨率预设；
    - 把窗口在屏幕上的偏移叠加到各识别区域。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
from typing import Any, Dict, Optional


GAME_TITLES = ("洛克王国", "Roco", "roco", "Kingdom", "kingdom")


def find_game_window() -> Optional[Dict[str, Any]]:
    """返回 ``{hwnd,title,x,y,w,h}`` 或 ``None``。

    规则：优先使用前台窗口命中的候选，否则挑客户区最大的候选。
    """
    try:
        user32 = ctypes.windll.user32
        EnumWindows = user32.EnumWindows
        GetForegroundWindow = user32.GetForegroundWindow
        GetWindowTextW = user32.GetWindowTextW
        IsWindowVisible = user32.IsWindowVisible
        GetClientRect = user32.GetClientRect
        ClientToScreen = user32.ClientToScreen

        EnumWindowsProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
        )

        candidates: list[tuple[int, str]] = []

        def enum_cb(hwnd, _lparam):
            if not IsWindowVisible(hwnd):
                return True
            buf = ctypes.create_unicode_buffer(256)
            GetWindowTextW(hwnd, buf, 256)
            title = buf.value
            if any(kw in title for kw in GAME_TITLES):
                candidates.append((int(hwnd), title))
            return True

        EnumWindows(EnumWindowsProc(enum_cb), 0)
        if not candidates:
            return None

        fg_hwnd = int(GetForegroundWindow() or 0)
        chosen: Optional[tuple[int, str]] = None
        if fg_hwnd:
            for h, t in candidates:
                if h == fg_hwnd:
                    chosen = (h, t)
                    break

        if chosen is None:
            def _client_area(hwnd: int) -> int:
                rect = ctypes.wintypes.RECT()
                try:
                    GetClientRect(hwnd, ctypes.byref(rect))
                    return max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
                except Exception:
                    return 0
            chosen = max(candidates, key=lambda item: _client_area(item[0]))

        hwnd, title = chosen
        rect = ctypes.wintypes.RECT()
        GetClientRect(hwnd, ctypes.byref(rect))
        w = int(rect.right - rect.left)
        h = int(rect.bottom - rect.top)
        if w <= 0 or h <= 0:
            return None

        pt = ctypes.wintypes.POINT(0, 0)
        ClientToScreen(hwnd, ctypes.byref(pt))
        return {
            "hwnd": hwnd,
            "title": title,
            "x": int(pt.x),
            "y": int(pt.y),
            "w": w,
            "h": h,
        }
    except Exception:
        return None


def _offset_region(region: Dict[str, int], ox: int, oy: int) -> Dict[str, int]:
    r = dict(region or {})
    if "left" in r:
        r["left"] = int(r.get("left", 0)) + int(ox)
    if "top" in r:
        r["top"] = int(r.get("top", 0)) + int(oy)
    return r


def _store_window_meta(cfg: Dict[str, Any], ox: int, oy: int, w: int, h: int) -> None:
    cfg["window_offset"] = {"x": ox, "y": oy, "w": w, "h": h}
    cfg["window_client_size"] = {"w": w, "h": h}


def _apply_window_regions(cfg: Dict[str, Any], base_regions: Dict[str, Dict[str, int]], ox: int, oy: int) -> None:
    for key in ("middle_region", "header_region"):
        region = base_regions.get(key)
        if isinstance(region, dict):
            cfg[key] = _offset_region(region, ox, oy)
    name_region = base_regions.get("name_in_header")
    if isinstance(name_region, dict):
        cfg["name_in_header"] = dict(name_region)


def apply_game_window(cfg: Dict[str, Any], info: Dict[str, Any]) -> str:
    """按窗口信息调整 cfg：套分辨率预设并叠加窗口偏移。"""
    from .utils import apply_resolution_preset
    ox, oy = int(info["x"]), int(info["y"])
    w, h = int(info["w"]), int(info["h"])
    _store_window_meta(cfg, ox, oy, w, h)
    mode, base_regions = apply_resolution_preset(cfg, f"{w}x{h}", apply_to_cfg=False)
    _apply_window_regions(cfg, base_regions, ox, oy)
    cfg["active_resolution"] = f"{w}x{h}"
    return mode


def refresh_window_offset(cfg: Dict[str, Any]) -> bool:
    """运行时刷新窗口位置，避免拖动后坐标失效。返回是否成功更新。"""
    from .utils import apply_resolution_preset
    info = find_game_window()
    if not info:
        return False
    try:
        ox, oy = int(info["x"]), int(info["y"])
        w, h = int(info["w"]), int(info["h"])

        _store_window_meta(cfg, ox, oy, w, h)
        _mode, base_regions = apply_resolution_preset(cfg, f"{w}x{h}", apply_to_cfg=False)
        _apply_window_regions(cfg, base_regions, ox, oy)

        return True
    except Exception:
        return False
