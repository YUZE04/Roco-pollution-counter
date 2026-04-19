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


# ---- 中文路径兼容：必要时用 Windows 8.3 短路径重启 --------------------------

def _maybe_relaunch_with_short_path() -> None:
    """PaddleOCR / PaddlePaddle 的 C++ 后端用 `std::ifstream` 打开模型配置，
    该流在 Windows 上不支持 UTF-8 路径（使用 ANSI code page）。
    如果 exe 安装路径含非 ASCII（如中文），用 Windows 8.3 短路径替身重新启动自己，
    子进程看到的 sys.executable / sys._MEIPASS 就都是纯 ASCII 了。
    """
    if sys.platform != "win32":
        return
    if not getattr(sys, "frozen", False):
        return  # 源码运行，不重启
    if os.environ.get("POLLUTION_COUNTER_SHORTPATH_RELAUNCHED") == "1":
        return  # 已经重启过，避免无限循环

    exe = sys.executable
    try:
        exe.encode("ascii")
        return  # 本身就是 ASCII
    except UnicodeEncodeError:
        pass

    try:
        GetShortPathNameW = ctypes.windll.kernel32.GetShortPathNameW
        GetShortPathNameW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
        GetShortPathNameW.restype = ctypes.c_uint32
        buf = ctypes.create_unicode_buffer(4096)
        n = GetShortPathNameW(exe, buf, len(buf))
        if n == 0 or n >= len(buf):
            _boot_log("shortpath: GetShortPathNameW failed", f"exe={exe}")
            return
        short = buf.value
    except Exception as e:
        _boot_log("shortpath: ctypes 调用异常", f"{e!r}")
        return

    try:
        short.encode("ascii")
    except UnicodeEncodeError:
        _boot_log("shortpath: 短路径仍含非 ASCII", f"short={short}")
        return

    if short.lower() == exe.lower():
        return  # 没有差异

    _boot_log("shortpath: 用短路径重启", f"from={exe}\nto  ={short}")
    os.environ["POLLUTION_COUNTER_SHORTPATH_RELAUNCHED"] = "1"
    try:
        os.execv(short, [short] + sys.argv[1:])
    except Exception as e:
        _boot_log("shortpath: os.execv 失败", f"{e!r}")


_maybe_relaunch_with_short_path()


# ---- 预检：扫描关键模型/配置目录，发现 0 字节文件即是解压损坏 ----------------

def _preflight_check_corrupt_files() -> None:
    if not getattr(sys, "frozen", False):
        return
    root = Path(sys.executable).resolve().parent
    # 只扫最关键的几个目录，避免耗时过长
    scan_dirs = [
        root / "_internal" / "paddle",
        root / "_internal" / "paddlex",
        root / "_internal" / "paddleocr",
        root / "paddleocr_models",
        root / "_internal" / "paddleocr_models",
    ]
    suspicious = []
    for d in scan_dirs:
        if not d.exists():
            continue
        try:
            for p in d.rglob("*"):
                if not p.is_file():
                    continue
                # 只关心配置/模型元数据类文件
                if p.suffix.lower() in {".json", ".yaml", ".yml", ".txt"} and p.stat().st_size == 0:
                    suspicious.append(p)
                    if len(suspicious) > 10:
                        break
            if len(suspicious) > 10:
                break
        except Exception as e:
            _boot_log("preflight: 扫描目录异常", f"dir={d} err={e!r}")

    if suspicious:
        sample = "\n".join(f"  - {p}" for p in suspicious[:5])
        msg = (
            "检测到 0 字节的配置文件（共 " + str(len(suspicious)) + " 个）：\n\n"
            + sample
            + "\n\n这通常是 zip 解压不完整 / 被杀毒软件拦截。请：\n"
            "  1) 用 7-Zip 或 Bandizip 重新解压 zip（不要用 Windows 自带解压）\n"
            "  2) 把整个文件夹加入杀毒软件白名单\n"
            "  3) 把安装路径换到纯英文目录，如 D:\\RocoPC"
        )
        _boot_log("preflight: 发现 0 字节文件", msg)
        _boot_msgbox(msg)
        sys.exit(2)


_preflight_check_corrupt_files()


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
