"""OCR 封装：复用旧版 `1.py` 里已经跑通的 `LocalPaddleOCRReader`。

旧版 1.py 里包含对 paddleocr/paddlex 的一系列运行时补丁（DLL 搜索路径、CPU 模式强制、
中文路径兼容等），代码量较大。为了快速迁移，我们直接动态加载 1.py 作为 `legacy_pc`
模块，并从中拿到 OCR 类及其依赖的工具函数。

这样做的代价：加载时会 `import keyboard` / `tkinter` 等旧依赖，但不会启动旧版 UI
（旧版的 `App().run()` 位于 `if __name__ == "__main__":` 分支中）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_LEGACY_MODULE_NAME = "roco_pc_legacy"


def _load_legacy_module():
    if _LEGACY_MODULE_NAME in sys.modules:
        return sys.modules[_LEGACY_MODULE_NAME]
    legacy_path = Path(__file__).resolve().parent.parent.parent / "1.py"
    if not legacy_path.exists():
        raise FileNotFoundError(f"旧版 1.py 未找到：{legacy_path}")
    spec = importlib.util.spec_from_file_location(_LEGACY_MODULE_NAME, str(legacy_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"无法创建 1.py 的 module spec: {legacy_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_LEGACY_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


_legacy = _load_legacy_module()

# 对外暴露
LocalPaddleOCRReader = _legacy.LocalPaddleOCRReader
