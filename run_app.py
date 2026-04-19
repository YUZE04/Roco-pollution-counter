"""PyInstaller 入口：单独一个文件，方便 spec 指向它。

用法：
    py run_app.py              # 本地开发运行
    pyinstaller 污染计数器v1.2.spec

重要：本文件负责**最早期**的崩溃捕获。
其它机器上"双击没反应"大多是 PyQt6 / PaddleOCR 等在 import 阶段就加载失败，
晚一点的 try/except 根本跑不到。所以这里在 import app.main 之前就要装好日志。
"""

from __future__ import annotations

import ctypes
import faulthandler
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path


# ---- 最早期的诊断日志设施 ----------------------------------------------------

def _runtime_dir() -> Path:
    """exe 同级目录（打包后）/ 源码根目录（开发时）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


_BOOT_LOG = _runtime_dir() / "startup_error.log"


def _boot_log(title: str, details: str = "") -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    block = [
        f"[{stamp}] {title}",
        f"python={sys.version}",
        f"frozen={getattr(sys, 'frozen', False)}",
        f"executable={sys.executable}",
        f"argv={sys.argv}",
        f"cwd={os.getcwd()}",
        f"sys.path[0:3]={sys.path[:3]}",
    ]
    if details:
        block.append(details.rstrip())
    block.append("")
    try:
        with _BOOT_LOG.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(block) + "\n")
    except Exception:
        # 连日志都写不进去（例如目录只读），就退回到临时目录
        try:
            import tempfile
            fallback = Path(tempfile.gettempdir()) / "污染计数器_startup_error.log"
            with fallback.open("a", encoding="utf-8") as fh:
                fh.write("\n".join(block) + "\n")
        except Exception:
            pass


def _boot_msgbox(msg: str) -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.user32.MessageBoxW(0, msg, "污染计数器 启动失败", 0x10)
    except Exception:
        pass


# 打开 faulthandler，把底层崩溃（段错误 / Qt 插件加载失败等）也落盘
try:
    _fh_file = open(_BOOT_LOG, "a", encoding="utf-8", buffering=1)
    faulthandler.enable(file=_fh_file, all_threads=True)
except Exception:
    pass


def _early_excepthook(exc_type, exc_value, exc_tb):
    details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    _boot_log("Unhandled exception (early)", details)
    _boot_msgbox(
        "程序启动时发生异常：\n\n"
        f"{exc_type.__name__}: {exc_value}\n\n"
        f"详细日志：{_BOOT_LOG}"
    )


sys.excepthook = _early_excepthook


# 记录一次"我进来了"，方便判断是不是连 Python 入口都没跑到
_boot_log("run_app.py: boot begin")


# ---- 真正的导入与启动 --------------------------------------------------------

try:
    from app.main import main
except BaseException as e:  # noqa: BLE001 - 连 SystemExit 也要抓，方便定位
    details = traceback.format_exc()
    _boot_log("Import app.main failed", details)
    _boot_msgbox(
        "加载主模块失败（通常是依赖缺失或损坏）：\n\n"
        f"{type(e).__name__}: {e}\n\n"
        f"详细日志：{_BOOT_LOG}\n\n"
        "常见原因：\n"
        "  1) 解压不完整，缺少 .dll / .pyd 文件\n"
        "  2) 安装路径或上级目录含特殊字符 / 只读\n"
        "  3) 缺少 VC++ 运行库 (vc_redist.x64.exe)\n"
    )
    sys.exit(1)


if __name__ == "__main__":
    try:
        _boot_log("run_app.py: calling main()")
        rc = main()
        _boot_log(f"run_app.py: main() returned {rc}")
        sys.exit(rc)
    except SystemExit:
        raise
    except BaseException as e:  # noqa: BLE001
        details = traceback.format_exc()
        _boot_log("main() raised", details)
        _boot_msgbox(
            f"程序运行中崩溃：\n\n{type(e).__name__}: {e}\n\n详细日志：{_BOOT_LOG}"
        )
        sys.exit(1)
