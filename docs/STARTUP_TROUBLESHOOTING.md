# 应用闪退问题诊断指南

## 问题现象
应用启动后立即闪退，看不到任何错误信息。

## 快速诊断步骤

### 1. 查看错误日志
应用启动失败时会在同目录创建 `startup_error.log` 文件：

```
污染计数器v1.2.2.exe 同目录
├── startup_error.log        ← 错误日志在这里
├── pollution_config.json
└── ...
```

**查看方法：**
- 右键 → 属性 → 打开文件位置
- 在应用目录找到 `startup_error.log` 文件
- 用记事本打开查看错误内容

### 2. 运行诊断工具
如果是从源代码运行，可以执行诊断脚本：

```bash
python diagnose_startup.py
```

这会检查：
- ✓ Python 版本
- ✓ 依赖库是否可用
- ✓ 应用模块是否可导入
- ✓ 必要的文件和目录

### 3. 常见问题和解决方案

#### 问题：缺少 PyQt6
**症状：** `ImportError: No module named 'PyQt6'`

**原因：**
- 依赖库不完整
- 某些依赖被误删或损坏

**解决：**
- 重新下载完整版本
- 确保 `_internal` 文件夹完整（包含所有 DLL 和库文件）

#### 问题：管理员权限请求失败
**症状：** `UAC elevation failed` 在日志中出现

**解决：**
- 右键应用 → "以管理员身份运行"

#### 问题：启动时快速闪退，无错误信息
**症状：** 看不到任何错误提示

**解决步骤：**

1. **打开命令行**
   - Win+R → 输入 `cmd` → 回车

2. **进入应用目录**
   ```bash
   cd "C:\Users\你的用户名\...污染计数器v1.2.2"
   ```

3. **直接运行 exe**（这样会保留控制台输出）
   ```bash
   污染计数器v1.2.2.exe
   ```

4. **查看错误信息**
   - 如果有错误会显示在控制台

#### 问题：缺少 VC++ 运行库
**症状：** 弹出 "缺少 VCRUNTIME140.dll" 或类似提示

**解决：**
- 从 Microsoft 官网下载安装：
  - [Visual C++ 运行库](https://support.microsoft.com/zh-cn/help/2977003/the-latest-supported-visual-c-downloads)
  - 选择 2015-2022 版本的 x64 (如果是 64 位系统)

#### 问题：某个模型文件损坏
**症状：** 日志显示 `PaddleOCR` 或 `paddleocr_models` 错误

**解决：**
- 删除 `paddleocr_models` 文件夹
- 重新启动应用，它会自动重新下载模型

---

## 高级诊断

### 启用调试模式（仅源代码）

编辑 `app/main.py`，在函数开始添加：

```python
def main() -> int:
    import logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    # ... 其余代码
```

### 查看详细启动日志

如果是打包版本，修改 spec 文件中的：

```python
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='污染计数器v1.2.2',
    debug=False,           # ← 改成 True
    console=False,         # ← 改成 True
    ...
)
```

然后重新打包：

```bash
pyinstaller 污染计数器v1.2.spec
```

---

## 收集诊断信息（发送给开发者）

如果问题无法自己解决，请提供：

1. **Windows 版本**
   - Win+R → `winver` → 查看版本信息

2. **错误日志**
   - `startup_error.log` 的完整内容

3. **系统信息**
   - 运行 `python diagnose_startup.py` 的输出

4. **发生的操作**
   - 是否修改过配置文件
   - 最后一次能正常启动是什么时候
   - 是否更新了系统或其他软件

---

## 常用命令

### 查看 startup_error.log 位置
```bash
python -c "from pathlib import Path; from app.backend.paths import RUNTIME_DIR; print(Path(RUNTIME_DIR) / 'startup_error.log')"
```

### 重置配置
```bash
del pollution_config.json
del pollution_count.json
```

重新启动应用，配置会被重置为默认值。

### 清理临时文件
```bash
del startup_error.log
del *.log
rmdir /s /q __pycache__
```
