#!/usr/bin/env python3
"""简单的打包测试。"""

import sys
sys.path.insert(0, '.')

print("测试 1: 导入 run_app...")
try:
    import run_app
    print("  ✓ OK")
except Exception as e:
    print(f"  ✗ 失败: {e}")
    import traceback
    traceback.print_exc()

print()
print("测试 2: 导入 app.main...")
try:
    from app import main
    print("  ✓ OK")
except Exception as e:
    print(f"  ✗ 失败: {e}")
    import traceback
    traceback.print_exc()

print()
print("测试完成")
