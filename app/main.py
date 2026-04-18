"""应用入口（PyQt6 + 真实后端）。

运行方法：
    py -m app.main
"""

from __future__ import annotations

import os
import sys
from typing import List, Tuple

# 抑制 "SetProcessDpiAwarenessContext() failed: 拒绝访问" 警告：
# python.exe 的 manifest/父进程已经设过 DPI 了，告诉 Qt 别再动它。
# 必须在 PyQt6 被 import 之前设置。
os.environ.setdefault("QT_QPA_PLATFORM_WINDOWS_OPTIONS", "dpiawareness=0")
# 再加一道保险：在 Qt 动手之前，自己先把进程的 DPI 感知设成 Per-Monitor v2
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.user32.SetProcessDpiAwarenessContext(
            ctypes.c_void_p(-4)  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        )
    except Exception:
        pass

from PyQt6.QtGui import QGuiApplication, QIcon
from PyQt6.QtWidgets import QApplication

from . import APP_VERSION
from .backend.paths import find_icon
from .controller import AppController
from .ui.main_window import MainWindow
from .ui.overlay import OverlayWindow


class Application:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setApplicationName("污染计数器")
        self.app.setApplicationDisplayName(f"污染计数器 {APP_VERSION}")

        icon_path = find_icon()
        if icon_path is not None:
            self.app.setWindowIcon(QIcon(str(icon_path)))

        # 控制器（拥有后端状态）
        self.controller = AppController()

        # 两个窗口
        self.main_window = MainWindow(controller=self.controller)
        self.overlay = OverlayWindow()

        # 接线
        self._wire()

        # 初始位置 + 初始数据
        self._place_overlay_initial()
        self._refresh_data()
        self._refresh_hotkey_hint()
        self.overlay.set_running(self.controller.running)
        self.overlay.set_locked(self.controller.locked)

    # ---------- 布局 ----------

    def _place_overlay_initial(self):
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        ow, oh = self.overlay.width(), self.overlay.height()
        cfg_overlay = self.controller.config.get("compact_window", {})
        x = cfg_overlay.get("x")
        y = cfg_overlay.get("y")
        if not isinstance(x, int) or not isinstance(y, int):
            x = geo.x() + geo.width() - ow - 20
            y = geo.y() + 80
        self.overlay.move(int(x), int(y))

    # ---------- 信号接线 ----------

    def _wire(self):
        c = self.controller
        m = self.main_window
        o = self.overlay

        # UI → 控制器
        m.toggle_monitor_requested.connect(c.toggle_monitor)
        m.show_overlay_requested.connect(self._show_overlay)
        m.quit_requested.connect(self._quit)
        m.reset_today_requested.connect(c.reset_today)
        m.hotkeys_changed.connect(self._refresh_hotkey_hint)

        o.toggle_monitor_requested.connect(c.toggle_monitor)
        o.toggle_lock_requested.connect(c.toggle_lock)
        o.show_main_requested.connect(self._show_main)
        o.manual_add_requested.connect(c.manual_add)
        o.manual_sub_requested.connect(c.manual_sub)
        o.quit_requested.connect(self._quit)

        # 控制器 → UI
        c.data_changed.connect(self._refresh_data)
        c.data_changed.connect(self.main_window._refresh_stats_tab)
        c.status_text_changed.connect(self.overlay.set_status_text)
        c.status_text_changed.connect(self.main_window.set_status_text)
        c.running_changed.connect(self.overlay.set_running)
        c.running_changed.connect(self.main_window.set_monitor_button_text)
        c.locked_changed.connect(self.overlay.set_locked)

    # ---------- 动作 ----------

    def _show_overlay(self):
        self.overlay.show()
        self.overlay.raise_()

    def _show_main(self):
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def _refresh_hotkey_hint(self):
        hk = self.controller.config.get("hotkeys", {})
        parts = []
        labels = [("start", "启"), ("pause", "暂"), ("lock", "锁"), ("add", "+"), ("sub", "-")]
        for key, label in labels:
            val = str(hk.get(key, "")).strip()
            if val:
                parts.append(f"{label}:{val}")
        self.overlay.set_hotkey_hint("  ".join(parts))

    def _refresh_data(self):
        d = self.controller.data
        self.overlay.set_total_count(d.total_count)
        self.overlay.set_current_species(d.last_species or "无")
        # 精灵列表：按今日计数降序
        today_counts = d.species_counts
        items: List[Tuple[str, int]] = sorted(
            today_counts.items(), key=lambda kv: (-kv[1], kv[0])
        )
        self.overlay.set_species_list(items)

    def _quit(self):
        self.controller.shutdown()
        self.app.quit()

    # ---------- 生命周期 ----------

    def run(self) -> int:
        self.main_window.show()
        self.overlay.show()
        return self.app.exec()


def main() -> int:
    return Application().run()


if __name__ == "__main__":
    sys.exit(main())
