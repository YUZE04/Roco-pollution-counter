# 别人电脑上闪退 - 解决方案

## 问题
应用在别人的电脑上启动后立即闪退，没有任何错误提示。

## 已实施的改进

### 1. ✓ 增强错误捕获和日志
- `app/main.py` 现在在启动的每一步都捕获异常
- 错误会被详细记录到 `startup_error.log`
- 启动失败时会显示**具体的错误消息**而不是默默闪退

### 2. ✓ 更好的错误提示
当发生以下错误时，用户会看到具体提示：
- ❌ ImportError → "某个依赖库缺失"
- ❌ QApplication 初始化失败 → "无法初始化 Qt"
- ❌ 控制器初始化失败 → "应用控制器初始化失败"
- ❌ UI 初始化失败 → "UI 初始化失败"

### 3. ✓ 诊断工具
新增两个诊断工具，可以帮助识别问题：

**`diagnose_startup.py`** - 自动检查所有依赖
```bash
python diagnose_startup.py
```
这会显示：
- ✓ Python 版本
- ✓ 所有依赖库导入状态
- ✓ 必要的文件和目录
- ✓ 哪里出问题了

**`test_startup.py`** - 快速启动测试
```bash
python test_startup.py
```

### 4. ✓ 详细的故障排查指南
`STARTUP_TROUBLESHOOTING.md` 包含：
- 如何查看错误日志
- 常见问题及解决方案
- 高级诊断方法
- 如何发送错误报告给开发者

---

## 部署指南

### 对最终用户

1. **如果闪退**
   - 查看同目录的 `startup_error.log` 文件
   - 按 STARTUP_TROUBLESHOOTING.md 中的步骤操作

2. **如果还是不行**
   - 运行 `diagnose_startup.py` 查看诊断结果
   - 把 `startup_error.log` 和诊断结果发给开发者

3. **常见快速修复**
   - 缺 PyQt6 → 重新下载完整版本
   - 缺 VC++ 库 → 安装 Visual C++ 2015-2022 运行库
   - 管理员权限失败 → 手动右键"以管理员身份运行"

### 打包时的注意事项

确保 spec 文件中包含所有必要的隐藏导入：

```python
hiddenimports = [
    # PyQt6
    'PyQt6.sip', 'PyQt6.QtGui', 'PyQt6.QtCore', 'PyQt6.QtWidgets',
    # PaddleOCR
    'paddle', 'paddleocr', 'paddlex',
    # 其他依赖
    'cv2', 'numpy', 'keyboard', 'mss', 'yaml',
]
```

和所有 collect_all() 调用。

---

## 测试闪退场景

### 模拟缺少 PyQt6
在别人的电脑上卸载或隐藏 PyQt6，应用启动时会显示：
```
模块导入失败：No module named 'PyQt6'

这通常表示某个依赖库缺失或损坏。
请重新下载最新版本。

错误日志：C:\...\startup_error.log
```

### 模拟其他错误
在 controller.py 中故意破坏初始化代码，应该看到清晰的错误提示而不是无声闪退。

---

## 信息流

```
用户点击应用
    ↓
main() 启动
    ↓
【新】增强的异常捕获
    ├─ 导入异常? → 显示 "模块导入失败..."
    ├─ QApplication 初始化失败? → 显示 "无法初始化 Qt..."
    ├─ AppController 初始化失败? → 显示 "应用控制器初始化失败..."
    ├─ UI 初始化失败? → 显示 "UI 初始化失败..."
    └─ 其他异常? → 显示 "程序启动失败..."
    ↓
所有异常都被写到 startup_error.log
    ↓
用户可以
  1. 看到明确的错误提示
  2. 查看 startup_error.log 了解详情
  3. 运行诊断工具
  4. 按指南操作或发送错误报告
```

---

## 后续改进空间

1. **UI 日志查看器** - 在应用中添加"查看启动日志"按钮
2. **自动诊断** - 启动时自动检查依赖并报告
3. **在线诊断** - 把错误日志发送给服务器分析
4. **沙箱测试** - 在隔离环境中测试启动

---

## 总结

**改进前：** 应用闪退 → 用户不知道发生了什么 → 无法调试

**改进后：** 应用启动失败 → 显示具体错误信息 → 用户可以采取行动或提交错误报告

关键文件：
- `app/main.py` - 增强的异常捕获
- `diagnose_startup.py` - 诊断工具
- `STARTUP_TROUBLESHOOTING.md` - 故障排查指南
