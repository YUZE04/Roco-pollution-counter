#!/usr/bin/env python3
"""打包脚本 - 显示详细的错误信息。"""

import sys
import os
from pathlib import Path

# 设置工作目录
os.chdir(Path(__file__).parent)

print("=" * 70)
print("污染计数器 v1.2.2 - PyInstaller 打包")
print("=" * 70)
print()

print("步骤 1: 检查 spec 文件...")
spec_file = Path("污染计数器v1.2.spec")
if not spec_file.exists():
    print(f"✗ spec 文件不存在: {spec_file}")
    sys.exit(1)
print(f"✓ spec 文件存在: {spec_file}")

print()
print("步骤 2: 导入 PyInstaller...")
try:
    from PyInstaller import __main__ as pyi_main
    print(f"✓ PyInstaller 版本: {__import__('PyInstaller').__version__}")
except ImportError as e:
    print(f"✗ PyInstaller 导入失败: {e}")
    sys.exit(1)

print()
print("步骤 3: 运行 PyInstaller...")
print("-" * 70)

# 构建命令行参数
args = [
    "--noconfirm",
    "--clean",
    str(spec_file),
]

try:
    # 调用 PyInstaller
    pyi_main.run(args)
    print("-" * 70)
    print()
    print("=" * 70)
    print("✓ 打包完成！")
    print("=" * 70)
    print()
    print("输出位置:")
    print("  dist/污染计数器v1.2.2/污染计数器v1.2.2.exe")
    print()
    
except SystemExit as e:
    if e.code == 0:
        print("-" * 70)
        print()
        print("=" * 70)
        print("✓ 打包完成！")
        print("=" * 70)
        print()
        print("输出位置:")
        print("  dist/污染计数器v1.2.2/污染计数器v1.2.2.exe")
        print()
    else:
        print("-" * 70)
        print()
        print(f"✗ PyInstaller 返回错误代码: {e.code}")
        sys.exit(1)
        
except Exception as e:
    print("-" * 70)
    print()
    print(f"✗ 打包过程中发生错误:")
    import traceback
    traceback.print_exc()
    sys.exit(1)
