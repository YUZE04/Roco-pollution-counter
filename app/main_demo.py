"""应用入口（PyQt6）。

当前阶段：骨架演示。运行后会看到：
- 一个紫黑色悬浮窗（默认右上角），显示假数据
- 一个主配置窗，可打开/切换悬浮窗、切换监测

启动方法：
    py -m app.main
"""

from __future__ import annotations

import sys
from typing import Optional

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QGuiApplication, QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from . import APP_VERSION
from .ui.main_window import MainWindow
from .ui.overlay import OverlayWindow


class Application:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setApplicationName("污染计数器")
        self.app.setApplicationDisplayName(f"污染计数器 {APP_VERSION}")

        # 图标
        try:
            self.app.setWindowIcon(QIcon("roco_counter_icon.ico"))
        except Exception:
            pass

        # 两个窗口
        self.main_window = MainWindow()
        self.overlay = OverlayWindow()

        # 状态
        self._running = False
        self._locked = False

        # 骨架假数据
        self._fake_count = 0

        # 信号接线
        self._wire_signals()

        # 悬浮窗初始位置：主屏右上角
        self._place_overlay_initial()

        # 演示用定时器：每秒增加一个假数字
        self._demo_timer = QTimer()
        self._demo_timer.setInterval(1000)
        self._demo_timer.timeout.connect(self._demo_tick)
        self._demo_timer.start()

        # 初始数据
        self.overlay.set_total_count(0)
        self.overlay.set_current_species("（等待检测）")
        self.overlay.set_species_list([
            ("示例精灵A", 3),
            ("示例精灵B", 2),
            ("示例精灵C", 1),
        ])
        self.overlay.set_running(False)
        self.overlay.set_locked(False)

    # ---------- 布局 ----------

    def _place_overlay_initial(self):
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        ow, oh = self.overlay.width(), self.overlay.height()
        x = geo.x() + geo.width() - ow - 20
        y = geo.y() + 80
        self.overlay.move(x, y)

    # ---------- 信号接线 ----------

    def _wire_signals(self):
        m = self.main_window
        o = self.overlay

        m.toggle_monitor_requested.connect(self._toggle_monitor)
        m.show_overlay_requested.connect(self._show_overlay)
        m.quit_requested.connect(self._quit)

        o.toggle_monitor_requested.connect(self._toggle_monitor)
        o.toggle_lock_requested.connect(self._toggle_lock)
        o.show_main_requested.connect(self._show_main)
        o.manual_add_requested.connect(self._manual_add)
        o.manual_sub_requested.connect(self._manual_sub)
        o.quit_requested.connect(self._quit)

    # ---------- 动作 ----------

    def _toggle_monitor(self):
        self._running = not self._running
        self.main_window.set_monitor_button_text(self._running)
        self.overlay.set_running(self._running)
        self.overlay.set_status_text("监测中" if self._running else "未启动")

    def _toggle_lock(self):
        self._locked = not self._locked
        self.overlay.set_locked(self._locked)

    def _show_overlay(self):
        self.overlay.show()
        self.overlay.raise_()

    def _show_main(self):
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def _manual_add(self):
        self._fake_count += 1
        self.overlay.set_total_count(self._fake_count)

    def _manual_sub(self):
        self._fake_count = max(0, self._fake_count - 1)
        self.overlay.set_total_count(self._fake_count)

    def _quit(self):
        self._demo_timer.stop()
        self.app.quit()

    # ---------- 假数据演示 ----------

    def _demo_tick(self):
        # 监测中才自增
        if self._running:
            self._fake_count += 1
            self.overlay.set_total_count(self._fake_count)

    def run(self) -> int:
        self.main_window.show()
        self.overlay.show()
        return self.app.exec()


def main() -> int:
    return Application().run()


if __name__ == "__main__":
    sys.exit(main())
