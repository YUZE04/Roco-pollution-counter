# 游戏窗口化模式识别失效修复

## 问题分析
当游戏以窗口化方式运行时，识别坐标不能随着窗口移动而自动调整，导致OCR扫描到错误位置。

**根本原因：**
- 旧版 1.py 在 `detect_loop()` 循环中没有在每一帧都刷新窗口偏移
- 只在初始检测时计算一次，后续窗口移动时坐标不更新

## 解决方案

### 1. 新增 `refresh_window_offset()` 函数 
**文件：** `app/backend/window_detect.py`

在检测循环的每一帧都调用此函数，实时刷新窗口位置：

```python
def refresh_window_offset(cfg: Dict[str, Any]) -> bool:
    """运行时刷新窗口位置，避免拖动后坐标失效。返回是否成功更新。"""
    # 1. 查找当前游戏窗口
    # 2. 获取窗口的屏幕偏移 (x, y)
    # 3. 重新计算识别区域的绝对坐标
    # 4. 更新配置中的 middle_region / header_region
```

### 2. 改进 `apply_resolution_preset()` 函数
**文件：** `app/backend/utils.py`

增加 `apply_to_cfg` 参数，支持两种工作模式：

```python
def apply_resolution_preset(
    cfg: dict, 
    preset: str, 
    apply_to_cfg: bool = True,
) -> str | tuple[str, dict]:
    """
    apply_to_cfg=True:  直接修改 cfg，返回模式描述 (str)
    apply_to_cfg=False: 仅返回缩放后的基础区域 ((str, dict))，不修改 cfg
    """
```

这样可以：
- 在初始检测时使用 `apply_to_cfg=False` 获取基础区域
- 然后手动应用窗口偏移
- 避免重复应用偏移导致的坐标错乱

### 3. 在检测循环中调用刷新函数
**文件：** `app/backend/detector.py`

在每一帧扫描前添加：

```python
cfg = self._get_cfg()

# 运行时刷新窗口位置，避免窗口移动后坐标失效
from .window_detect import refresh_window_offset
refresh_window_offset(cfg)

# 然后继续使用更新后的 cfg 进行 OCR 扫描
middle_region = dict(cfg["middle_region"])
...
```

## 修改文件清单

| 文件 | 改动 |
|-----|------|
| `app/backend/window_detect.py` | 新增 `refresh_window_offset()` + 辅助函数 |
| `app/backend/utils.py` | 改进 `apply_resolution_preset()` 增加 `apply_to_cfg` 参数 |
| `app/backend/detector.py` | 在检测循环中每帧调用 `refresh_window_offset()` |

## 工作流程

```
用户启动监测
    ↓
检测线程循环（每 0.7s 扫描一次）
    ↓
【新增】refresh_window_offset(cfg)
    ├─ 查找游戏窗口当前位置
    ├─ 获取屏幕偏移 (ox, oy)
    └─ 更新 cfg["middle_region"] 和 cfg["header_region"]
    ↓
使用更新后的坐标进行 OCR 扫描
    ↓
即使用户拖动窗口，下一帧会自动重新计算坐标 ✓
```

## 向后兼容性

- `apply_resolution_preset()` 的默认行为保持不变（`apply_to_cfg=True`）
- 所有调用该函数的地方无需修改
- 新增功能只在检测循环中使用，不影响其他模块

## 测试建议

1. **全屏模式**：正常运行，无差异
2. **窗口化模式**：
   - 启动监测
   - 拖动游戏窗口
   - ✓ 识别应该继续工作
   - ✓ 准确度应该和全屏一致

## 性能影响

- `refresh_window_offset()` 调用 `find_game_window()` 需要枚举所有窗口
- 每帧额外开销约 1-5ms（可接受）
- 可在前台窗口改变时才刷新（优化方向）
