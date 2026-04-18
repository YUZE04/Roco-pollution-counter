"""PyInstaller 入口：单独一个文件，方便 spec 指向它。

用法：
    py run_app.py              # 本地开发运行
    pyinstaller 污染计数器v1.2.spec
"""

from __future__ import annotations

import sys

from app.main import main


if __name__ == "__main__":
    sys.exit(main())
