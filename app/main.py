"""应用入口（PyQt6 + 真实后端）。

运行方法：
    py -m app.main
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

# ctypes 需要在 Windows 下很多地方用到（DPI、UAC、MessageBox），统一在顶层导入。
if sys.platform == "win32":
    import ctypes
else:
    ctypes = None  # type: ignore[assignment]

from . import APP_VERSION


# ---- 先装好崩溃日志，再 import 重型依赖 --------------------------------------
# 这样即使 PyQt6 / controller / ui 在 import 阶段就炸了，也能落盘。

def _early_runtime_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


STARTUP_ERROR_LOG = _early_runtime_dir() / "startup_error.log"


def _append_startup_error(title: str, details: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    block = [
        f"[{stamp}] {title}",
        f"version={APP_VERSION}",
        f"python={sys.version}",
        f"frozen={getattr(sys, 'frozen', False)}",
        f"executable={sys.executable}",
        f"argv={sys.argv}",
        details.rstrip(),
        "",
    ]
    try:
        with STARTUP_ERROR_LOG.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(block))
    except Exception:
        pass


def _show_fatal_error(message: str) -> None:
    if sys.platform != "win32" or ctypes is None:
        return
    try:
        ctypes.windll.user32.MessageBoxW(0, message, "污染计数器 启动失败", 0x10)
    except Exception:
        pass


def _install_crash_logging() -> None:
    def _handle_exception(exc_type, exc_value, exc_tb):
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        _append_startup_error("Unhandled exception", details)
        _show_fatal_error(
            "程序启动时发生异常，已写入 startup_error.log。\n"
            f"位置：{STARTUP_ERROR_LOG}"
        )

    def _handle_thread_exception(args):
        details = "".join(
            traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
        )
        thread_name = getattr(args.thread, "name", "unknown")
        _append_startup_error(f"Unhandled thread exception [{thread_name}]", details)

    sys.excepthook = _handle_exception
    if hasattr(threading, "excepthook"):
        threading.excepthook = _handle_thread_exception


# 模块一被加载就立刻生效（run_app.py 之外的入口也能受益，例如 py -m app.main）
_install_crash_logging()


# 抑制 "SetProcessDpiAwarenessContext() failed: 拒绝访问" 警告：
# python.exe 的 manifest/父进程已经设过 DPI 了，告诉 Qt 别再动它。
# 必须在 PyQt6 被 import 之前设置。
os.environ.setdefault("QT_QPA_PLATFORM_WINDOWS_OPTIONS", "dpiawareness=0")
# 再加一道保险：在 Qt 动手之前，自己先把进程的 DPI 感知设成 Per-Monitor v2
if sys.platform == "win32" and ctypes is not None:
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(
            ctypes.c_void_p(-4)  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        )
    except Exception:
        pass


# ---- 重型依赖：任何一个炸了都要记录到日志 ------------------------------------
try:
    from PyQt6.QtGui import QGuiApplication, QIcon
    from PyQt6.QtWidgets import QApplication

    from .backend.paths import RUNTIME_DIR, find_icon
    from .controller import AppController
    from .ui.main_window import MainWindow
    from .ui.overlay import OverlayWindow
except BaseException as _imp_err:  # noqa: BLE001
    _append_startup_error(
        "Top-level import failed in app.main",
        traceback.format_exc(),
    )
    _show_fatal_error(
        "加载依赖失败（通常是 PyQt6 / PaddleOCR 原生库未正确解压）：\n\n"
        f"{type(_imp_err).__name__}: {_imp_err}\n\n"
        f"详细日志：{STARTUP_ERROR_LOG}"
    )
    raise


def ensure_run_as_administrator() -> bool:
    """Windows：非管理员时请求 UAC 提权并重启当前入口。"""
    if sys.platform != "win32":
        return True
    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            return True
    except Exception:
        return True

    try:
        if getattr(sys, "frozen", False):
            executable = sys.executable
            params = subprocess.list2cmdline(sys.argv[1:])
        else:
            executable = sys.executable
            params = subprocess.list2cmdline(["-m", "app.main", *sys.argv[1:]])
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", executable, params or None, None, 1
        )
        if int(result) > 32:
            return False
    except Exception:
        pass

    try:
        ctypes.windll.user32.MessageBoxW(
            0,
            "无法请求管理员权限，请右键选择“以管理员身份运行”。",
            "需要管理员权限",
            0x10,
        )
    except Exception:
        pass
    return False


class Application:
    def __init__(self):
        try:
            self.app = QApplication(sys.argv)
        except Exception as e:
            _append_startup_error("QApplication initialization failed", 
                                 f"Exception: {e}\nTraceback: {traceback.format_exc()}")
            raise RuntimeError(f"无法初始化 Qt 应用：{e}") from e
        
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setApplicationName("污染计数器")
        self.app.setApplicationDisplayName(f"污染计数器 {APP_VERSION}")

        icon_path = find_icon()
        if icon_path is not None:
            self.app.setWindowIcon(QIcon(str(icon_path)))

        # 控制器（拥有后端状态）
        try:
            self.controller = AppController()
        except Exception as e:
            _append_startup_error("AppController initialization failed",
                                 f"Exception: {e}\nTraceback: {traceback.format_exc()}")
            raise RuntimeError(f"无法初始化应用控制器：{e}") from e

        # 两个窗口
        try:
            self.main_window = MainWindow(controller=self.controller)
            self.overlay = OverlayWindow()
        except Exception as e:
            _append_startup_error("UI initialization failed",
                                 f"Exception: {e}\nTraceback: {traceback.format_exc()}")
            raise RuntimeError(f"无法初始化 UI：{e}") from e

        # 接线
        self._wire()

        # 初始位置 + 初始数据
        self._place_overlay_initial()
        self._refresh_data()
        self._refresh_hotkey_hint()
        self.overlay.set_running(self.controller.running)
        self.overlay.set_paused(self.controller.paused)
        self.overlay.set_locked(self.controller.locked)
        self.main_window.set_paused_state(self.controller.paused)

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
        c.paused_changed.connect(self.overlay.set_paused)
        c.paused_changed.connect(self.main_window.set_paused_state)
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
        labels = [("start", "暂/继"), ("lock", "锁"), ("add", "+"), ("sub", "-")]
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
    """主入口。尽最大努力捕获和记录启动错误。"""
    _install_crash_logging()
    
    # 首先尝试无管理员权限启动，让用户看到真实错误而不是因为权限失败导致的闪退
    try:
        if not ensure_run_as_administrator():
            return 0
    except Exception as e:
        details = traceback.format_exc()
        _append_startup_error("UAC elevation exception", details)
        _show_fatal_error(
            f"管理员权限请求失败：{e}\n\n"
            f"请手动以管理员身份运行本程序。\n"
            f"错误日志：{STARTUP_ERROR_LOG}"
        )
        return 1
    
    try:
        return Application().run()
    except ImportError as e:
        details = traceback.format_exc()
        _append_startup_error("Import error during startup", details)
        error_msg = (
            f"模块导入失败：{e}\n\n"
            f"这通常表示某个依赖库缺失或损坏。\n"
            f"请重新下载最新版本。\n\n"
            f"错误日志：{STARTUP_ERROR_LOG}"
        )
        _show_fatal_error(error_msg)
        return 1
    except Exception as e:
        details = traceback.format_exc()
        _append_startup_error("Fatal startup exception", details)
        error_msg = (
            f"程序启动失败：{type(e).__name__}\n\n{str(e)}\n\n"
            f"完整错误日志已保存到：\n{STARTUP_ERROR_LOG}"
        )
        _show_fatal_error(error_msg)
        return 1


if __name__ == "__main__":
    sys.exit(main())
