# 污染计数器 v1.2.4 发布清单

**发布日期**：2026-04-19  
**版本号**：v1.2.4  
**GitHub 标签**：已创建并推送 ✅

---

## 📦 发布物件

### 打包文件信息
- **文件名**：`污染计数器v1.2.4.zip`
- **大小**：24.95 MB
- **位置**：`dist/污染计数器v1.2.4.zip`
- **创建时间**：2026-04-19 20:06:44
- **内容**：完整的可执行应用程序（包含所有依赖）

### 内部文件结构
```
污染计数器v1.2.4/
├── 污染计数器v1.2.4.exe          # 主执行程序
└── _internal/                      # 应用依赖库
    ├── 以下依赖已包含：
    ├── opencv-python (cv2)
    ├── paddleocr 及模型文件
    ├── PyQt6
    ├── numpy, scipy
    └── 其他 Python 运行时库
```

---

## ✨ 新增功能

### 1. 🎯 一键打开主窗口热键
- **快捷键**：键盘 `0`（默认）
- **功能**：快速打开主配置窗口，无需鼠标操作
- **可自定义**：在应用主窗口"设置→热键"标签页修改快捷键
- **实现文件**：`app/backend/hotkeys.py`, `app/ui/main_window.py`

### 2. 🌍 中文路径支持优化
- **改进**：完整支持中文路径下的污染检测和 OCR 识别
- **自动适配**：自动处理 PaddleOCR 在中文环境下的路径问题
- **无需配置**：开箱即用，无需手动设置
- **实现文件**：`1.py` 中的 `_ensure_ascii_model_dir()` 函数

---

## 🔄 版本变更

### 文件更新
- [x] `app/__init__.py` - 版本号更新到 `v1.2.4`
- [x] `version.json` - 新增版本元数据和下载链接
- [x] `污染计数器v1.2.spec` - PyInstaller 配置更新版本号
- [x] `app/backend/config.py` - 热键配置
- [x] `app/backend/hotkeys.py` - 热键系统增强
- [x] `app/ui/main_window.py` - UI 新增热键设置选项

### Git 提交信息
- **提交哈希**：f3def86
- **提交信息**：`v1.2.4: 一键打开主窗口热键 + 中文路径优化`
- **标签**：`v1.2.4`
- **远程状态**：✅ 已推送到 GitHub

---

## 📋 发布步骤

### ✅ 已完成
- [x] 代码更新
- [x] 版本号变更
- [x] PyInstaller 打包
- [x] ZIP 压缩
- [x] Git 提交
- [x] GitHub 标签创建
- [x] GitHub 推送

### ⏳ 待完成（手动操作）

#### 1️⃣ GitHub Release 发布
**步骤**：
1. 访问：https://github.com/YUZE04/Roco-pollution-counter/releases
2. 点击"Create a new release"或"Draft a new release"
3. 选择标签：`v1.2.4`
4. 填写标题：`v1.2.4 - 一键打开主窗口 + 中文路径优化`
5. 复制下方"发布说明"到描述框
6. 上传附件：`dist/污染计数器v1.2.4.zip`
7. 点击"Publish release"

#### 2️⃣ 夸克网盘上传
**步骤**：
1. 登录个人夸克网盘账户
2. 上传文件：`c:\Users\Administrator\污染计数器\dist\污染计数器v1.2.4.zip`
3. 设置分享权限（可选择公开分享）
4. 复制分享链接
5. 更新本地 `version.json` 中的 `download_url_quark` 字段为新链接
6. 提交更新到 GitHub

---

## 📝 发布说明文本

```markdown
## 污染计数器 v1.2.4 发布

### ✨ 新增功能

#### 🎯 一键打开主窗口热键
- 新增快捷键：按 **0** 快速打开主配置窗口
- 无需鼠标操作，直接键盘快速启动
- 可在主窗口 **设置→热键** 标签页自定义快捷键

#### 🌍 中文路径支持优化
- 完整支持中文路径下的污染检测
- 改进 PaddleOCR 在中文路径环境下的识别
- 自动适配中文路径，开箱即用
- 无需手动配置，智能识别系统环境

### 📊 技术改进
- 优化热键系统架构，支持快速窗口切换
- 增强路径处理逻辑，支持更多字符编码
- 改进 OCR 模型加载机制

### 🔗 下载链接
- **GitHub**：https://github.com/YUZE04/Roco-pollution-counter/releases/download/v1.2.4/污染计数器v1.2.4.zip
- **夸克网盘**：[在此粘贴分享链接]（上传后更新）

### 📦 文件信息
- 大小：~25 MB（包含所有依赖）
- 格式：ZIP 压缩包
- 使用方法：解压后直接运行 `污染计数器v1.2.4.exe`

### 🐛 已知问题
- 无已知问题

### 💡 建议
- 如遇到问题，请检查系统是否为 Windows 10 或更高版本
- 如有界面显示问题，尝试重启应用程序

---
祝您使用愉快！
```

---

## 🔗 重要链接

| 项目 | 链接 |
|:---|:---|
| GitHub 仓库 | https://github.com/YUZE04/Roco-pollution-counter |
| GitHub Releases | https://github.com/YUZE04/Roco-pollution-counter/releases |
| v1.2.4 标签 | https://github.com/YUZE04/Roco-pollution-counter/releases/tag/v1.2.4 |
| 打包文件路径 | `dist/污染计数器v1.2.4.zip` |

---

## 📄 相关配置文件

### version.json 更新内容
```json
{
  "version": "v1.2.4",
  "release_date": "2026-04-19",
  "download_url_github": "https://github.com/YUZE04/Roco-pollution-counter/releases/download/v1.2.4/污染计数器v1.2.4.zip",
  "download_url_quark": "[待上传更新]",
  "release_notes": "一键打开主窗口热键 + 中文路径优化"
}
```

---

## ✅ 发布完成度统计

| 任务 | 状态 | 备注 |
|:---|:---:|:---|
| 代码更新 | ✅ | 6 个文件已更新 |
| 版本号变更 | ✅ | 更新到 v1.2.4 |
| 功能测试 | ✅ | 基本功能正常 |
| PyInstaller 打包 | ✅ | 成功生成 exe |
| ZIP 压缩 | ✅ | 24.95 MB |
| Git 提交 | ✅ | 提交号：f3def86 |
| GitHub 推送 | ✅ | 已推送标签 v1.2.4 |
| GitHub Release | ⏳ | 待手动发布 |
| 夸克网盘上传 | ⏳ | 待手动上传 |

---

**发布状态**：**已就绪，等待最终上传** ✅

所有代码已完成、打包完成、推送完成。可随时进行 GitHub Release 发布和夸克网盘上传。
