#!/usr/bin/env python3
"""诊断启动问题 - 帮助识别闪退原因。"""

import sys
import traceback
from pathlib import Path

def check_python():
    print(f"✓ Python 版本: {sys.version}")
    print(f"✓ Python 可执行: {sys.executable}")
    print()

def check_imports():
    """检查关键依赖是否可导入。"""
    checks = [
        ("PyQt6", "PyQt6.QtWidgets"),
        ("PyQt6.QtCore", "PyQt6.QtCore"),
        ("cv2", "cv2"),
        ("numpy", "numpy"),
        ("paddle", "paddle"),
        ("paddleocr", "paddleocr"),
        ("paddlex", "paddlex"),
        ("mss", "mss"),
        ("keyboard", "keyboard"),
        ("yaml", "yaml"),
    ]
    
    failed = []
    for name, module in checks:
        try:
            __import__(module)
            print(f"✓ {name}: OK")
        except ImportError as e:
            print(f"✗ {name}: 导入失败 - {e}")
            failed.append(name)
        except Exception as e:
            print(f"⚠ {name}: 导入时异常 - {e}")
            failed.append(name)
    
    print()
    if failed:
        print(f"❌ {len(failed)} 个模块导入失败: {', '.join(failed)}")
        return False
    else:
        print("✓ 所有关键模块导入成功")
        return True

def check_app_imports():
    """检查应用本身的导入。"""
    print("检查应用模块...")
    try:
        # 这会触发app的导入，可能暴露问题
        from app import main
        print("✓ app.main: OK")
    except Exception as e:
        print(f"✗ app.main 导入失败:")
        traceback.print_exc()
        return False
    
    return True

def check_paths():
    """检查必要的路径和文件。"""
    print("检查路径和文件...")
    checks = [
        ("app 目录", Path("app").is_dir()),
        ("paddleocr_models 目录", Path("paddleocr_models").is_dir()),
        (
            "pollution_config(.example).json",
            Path("pollution_config.json").exists() or Path("pollution_config.example.json").exists(),
        ),
        (
            "pollution_count(.example).json",
            Path("pollution_count.json").exists() or Path("pollution_count.example.json").exists(),
        ),
        ("version.json", Path("version.json").exists()),
    ]
    
    failed = []
    for name, result in checks:
        status = "✓" if result else "✗"
        print(f"{status} {name}")
        if not result:
            failed.append(name)
    
    print()
    if failed:
        print(f"❌ {len(failed)} 个文件/目录缺失: {', '.join(failed)}")
        return False
    else:
        print("✓ 所有必要的文件/目录都存在")
        return True

def main():
    print("=" * 60)
    print("污染计数器 - 启动诊断工具")
    print("=" * 60)
    print()
    
    check_python()
    
    print("检查依赖库...")
    print("-" * 60)
    imports_ok = check_imports()
    
    print("检查应用模块...")
    print("-" * 60)
    app_ok = check_app_imports()
    
    print("检查文件系统...")
    print("-" * 60)
    paths_ok = check_paths()
    
    print()
    print("=" * 60)
    if imports_ok and app_ok and paths_ok:
        print("✓ 诊断完成：一切正常，应该可以启动")
        print("=" * 60)
        return 0
    else:
        print("❌ 诊断完成：发现问题，详见上方")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
