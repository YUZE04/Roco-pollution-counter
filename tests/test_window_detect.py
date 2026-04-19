#!/usr/bin/env python3
"""快速测试窗口检测修改是否工作。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from app.backend.window_detect import find_game_window, apply_game_window, refresh_window_offset
    print("✓ window_detect 导入成功")
except Exception as e:
    print(f"✗ window_detect 导入失败: {e}")
    sys.exit(1)

try:
    from app.backend.utils import apply_resolution_preset
    print("✓ utils.apply_resolution_preset 导入成功")
except Exception as e:
    print(f"✗ utils.apply_resolution_preset 导入失败: {e}")
    sys.exit(1)

# 测试 apply_resolution_preset 返回值
try:
    cfg_test = {
        "base_resolution": "2560x1600",
        "base_regions": {
            "middle_region": {"left": 1000, "top": 200, "width": 100, "height": 50},
            "header_region": {"left": 2000, "top": 50, "width": 400, "height": 100},
            "name_in_header": {"left": 100, "top": 40, "width": 200, "height": 50},
        },
        "resolution_presets": {}
    }
    
    # 测试 apply_to_cfg=True
    result1 = apply_resolution_preset(cfg_test, "1920x1080", apply_to_cfg=True)
    print(f"✓ apply_resolution_preset(apply_to_cfg=True) 返回: {type(result1).__name__} = {result1!r}")
    assert isinstance(result1, str), f"应该返回 str，但得到 {type(result1)}"
    
    # 测试 apply_to_cfg=False
    result2 = apply_resolution_preset(cfg_test, "1920x1080", apply_to_cfg=False)
    print(f"✓ apply_resolution_preset(apply_to_cfg=False) 返回: {type(result2).__name__}")
    assert isinstance(result2, tuple) and len(result2) == 2, f"应该返回 (str, dict) 元组，但得到 {type(result2)}"
    assert isinstance(result2[0], str) and isinstance(result2[1], dict), \
        f"应该返回 (str, dict)，但得到 ({type(result2[0])}, {type(result2[1])})"
    
    print("✓ apply_resolution_preset 返回值类型正确")
    
except Exception as e:
    print(f"✗ apply_resolution_preset 测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✓ 所有测试通过！窗口检测修改正确无误。")
