"""Windows 11 原生材质效果（Mica / Acrylic）。

关键：**不要**和 ``WA_TranslucentBackground`` 一起用。后者会让 Qt 用
WS_EX_LAYERED 分层窗口，DWM 不会合成 Mica 材质。正确做法是：

1. 窗口不设透明属性；用 QSS 把背景画成 ``transparent`` 让 Qt 不填充；
2. 调 ``DwmExtendFrameIntoClientArea`` 把玻璃延伸到整个客户区；
3. 再调 ``DwmSetWindowAttribute(DWMWA_SYSTEMBACKDROP_TYPE, ...)``。
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from ctypes.wintypes import DWORD, HWND, LONG, LPARAM, UINT, WPARAM
from enum import IntEnum

from PyQt6.QtWidgets import QWidget


class BackdropType(IntEnum):
    AUTO = 0
    NONE = 1
    MICA = 2        # 带桌面壁纸色调
    ACRYLIC = 3     # 半透明毛玻璃（更强的 blur）
    MICA_ALT = 4    # Mica 加强版（更饱和）


_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_SYSTEMBACKDROP_TYPE = 38


class _MARGINS(ctypes.Structure):
    _fields_ = [
        ("cxLeftWidth", ctypes.c_int),
        ("cxRightWidth", ctypes.c_int),
        ("cyTopHeight", ctypes.c_int),
        ("cyBottomHeight", ctypes.c_int),
    ]


def _get_hwnd(window: QWidget) -> int | None:
    try:
        return int(window.winId())
    except Exception:
        return None


def _dwm_set(hwnd: int, attr: int, value: int) -> bool:
    try:
        val = ctypes.c_int(value)
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            wintypes.DWORD(attr),
            ctypes.byref(val),
            ctypes.sizeof(val),
        )
        return result == 0
    except Exception:
        return False


def _extend_frame(hwnd: int) -> bool:
    """把 DWM 玻璃 frame 延伸到整个客户区（Mica 的前提之一）。"""
    try:
        margins = _MARGINS(-1, -1, -1, -1)
        result = ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(
            wintypes.HWND(hwnd), ctypes.byref(margins)
        )
        return result == 0
    except Exception:
        return False


def enable_dark_titlebar(window: QWidget) -> bool:
    if sys.platform != "win32":
        return False
    hwnd = _get_hwnd(window)
    if hwnd is None:
        return False
    return _dwm_set(hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE, 1)


_DWMWA_USE_HOSTBACKDROPBRUSH = 17
_DWMWA_MICA_EFFECT = 1029  # legacy (Win11 pre-22H2)


def enable_mica(window: QWidget, *, kind: BackdropType = BackdropType.MICA) -> bool:
    """对 ``window`` 启用 Mica/Acrylic 背景。

    调用方**不应**设置 ``WA_TranslucentBackground=True``。应让窗口根背景通过
    QSS 设成 ``transparent``，DWM 会自己把 Mica 画在 Qt 绘制之下。

    Mica 渲染需要 DWM 合成通过。在 frameless (WS_POPUP) 窗口上 DWM 有时会
    拒绝应用——这里连带调用 ``DWMWA_USE_HOSTBACKDROPBRUSH``（popup 专用）
    和 legacy 的 ``DWMWA_MICA_EFFECT`` 双保险。
    """
    if sys.platform != "win32":
        return False
    hwnd = _get_hwnd(window)
    if hwnd is None:
        return False

    # 1. 暗色标题栏 + popup 背景刷保险
    _dwm_set(hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE, 1)
    _dwm_set(hwnd, _DWMWA_USE_HOSTBACKDROPBRUSH, 1)
    # 2. 玻璃 frame 覆盖整个客户区
    _extend_frame(hwnd)
    # 3. 设置材质类型（Win11 22H2+）
    ok_new = _dwm_set(hwnd, _DWMWA_SYSTEMBACKDROP_TYPE, int(kind))
    # 4. Legacy Mica flag（Win11 21H2 / insider 预览版）
    ok_legacy = _dwm_set(hwnd, _DWMWA_MICA_EFFECT, 1)
    return ok_new or ok_legacy


# ---------------------------------------------------------------- NCCALCSIZE

_WM_NCCALCSIZE = 0x0083


def handle_nccalcsize(message) -> tuple[bool, int]:
    """Qt ``nativeEvent`` 的辅助：拦截 ``WM_NCCALCSIZE`` 消除非客户区。

    返回 ``(handled, result)``。用法::

        def nativeEvent(self, et, msg):
            from .win_effects import handle_nccalcsize
            h, r = handle_nccalcsize(msg)
            if h:
                return True, r
            return super().nativeEvent(et, msg)

    当 ``wParam=TRUE`` 时直接返回 ``0``，Windows 会把 ``rgrc[0]`` （即整个
    窗口矩形）当作新的客户区，标题栏和边框被吃掉。窗口保留
    WS_OVERLAPPEDWINDOW 风格 → DWM Mica 能稳定应用，但视觉上无 frame。

    注意：必须用 ``wintypes.MSG``（其中 WPARAM = c_ulonglong 在 64-bit 上
    是 8 字节），不能自己用 ``wintypes.WPARAM``（那是 c_ulong = 4 字节，
    64-bit 下结构体偏移全错、会栈损坏）。
    """
    if sys.platform != "win32":
        return False, 0
    try:
        native_msg = ctypes.cast(
            int(message), ctypes.POINTER(wintypes.MSG)
        ).contents
        if native_msg.message == _WM_NCCALCSIZE and native_msg.wParam:
            return True, 0
    except Exception:
        pass
    return False, 0
