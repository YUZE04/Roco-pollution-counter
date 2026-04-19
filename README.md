<div align="center">

<img src="roco_counter_icon.ico" width="96" height="96" alt="icon" />

# 🧪 污染计数器 · Roco Pollution Counter

> **洛克王国世界污染追踪桌面工具** · 悬浮窗 + OCR 自动计数 + 全局热键

[![Version](https://img.shields.io/badge/version-v1.2.3-8B5CF6?style=flat-square)](https://github.com/YUZE04/Roco-pollution-counter/releases/latest)
[![Platform](https://img.shields.io/badge/platform-Windows-0078D6?style=flat-square&logo=windows&logoColor=white)](https://github.com/YUZE04/Roco-pollution-counter/releases/latest)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-41CD52?style=flat-square&logo=qt&logoColor=white)](https://doc.qt.io/qtforpython-6/)
[![OCR](https://img.shields.io/badge/OCR-PaddleOCR-FF4B4B?style=flat-square)](https://github.com/PaddlePaddle/PaddleOCR)
[![License](https://img.shields.io/badge/license-AGPL--3.0-green?style=flat-square)](./LICENSE)
[![Release](https://img.shields.io/github/v/release/YUZE04/Roco-pollution-counter?style=flat-square&logo=github)](https://github.com/YUZE04/Roco-pollution-counter/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/YUZE04/Roco-pollution-counter/total?style=flat-square&logo=github&color=brightgreen)](https://github.com/YUZE04/Roco-pollution-counter/releases)

[⬇️ 下载最新版](https://github.com/YUZE04/Roco-pollution-counter/releases/latest) ·
[📝 更新日志](#-更新日志--changelog) ·
[🐛 反馈问题](https://github.com/YUZE04/Roco-pollution-counter/issues) ·
[🎵 抖音 @conflicto834](https://www.douyin.com/)

</div>

---

## ✨ 这是什么 · What is this

一个在玩洛克王国时 **边玩边自动记** 世界污染次数的桌面小工具。后台 OCR 读游戏画面里的关键词，命中一次就自动 +1，还能按精灵分类统计、看每日曲线、用热键手动 ± 修正。

A lightweight Windows overlay that **auto-counts world-pollution events in Roco Kingdom** via screen OCR, with per-species stats, daily charts, manual hotkeys, and a transparent always-on-top HUD.

<div align="center">

> 🔒 锁定后鼠标完全穿透 · ⚡ 毫秒级热键 · 🎨 半透明玻璃风 · 📊 今日 / 累计双维度统计

</div>

---

## 🎯 功能亮点 · Highlights

| | 功能 | 说明 |
|:-:|:--|:--|
| 🤖 | **OCR 自动计数** | PaddleOCR 本地模型，零网络依赖 |
| 🎛️ | **全局热键** | Win32 轮询，不吃鼠标性能 |
| 🪟 | **悬浮 HUD** | 无边框 + 始终置顶 + 玻璃材质 |
| 🔒 | **一键锁定** | 整窗鼠标穿透，不挡游戏操作 |
| 🖥️ | **分辨率自适应** | 预设 + 按比例缩放，支持 150% DPI |
| 📆 | **每日 / 累计** | 按日期 + 按精灵双维度统计 |
| 🧩 | **OCR 纠错** | 可配置别名表，一键修正常见误识别 |
| 🔄 | **在线更新** | 启动自动检查 GitHub Release |
| 🩺 | **启动诊断** | 崩溃自动落盘 `startup_error.log`，远程排障友好 |

---

## 📦 下载安装 · Download

<div align="center">

### 👉 [点这里下载最新 Release](https://github.com/YUZE04/Roco-pollution-counter/releases/latest) 👈

</div>

- **解压后** 双击 `污染计数器v1.2.3.exe` 即可运行（建议 **以管理员身份运行**）。
- 解压路径避开只读目录（如 `Program Files`）；桌面 / D 盘自建文件夹最稳。
- 打不开？先装 [VC++ 运行库](https://aka.ms/vs/17/release/vc_redist.x64.exe)，再把 exe 加入杀软白名单。
- 仍然打不开？把 exe 同级目录下的 `startup_error.log` 发给作者 🩺

---

## ⌨️ 默认热键 · Default Hotkeys

| 热键 | 作用 |
|:-:|:--|
| `7` | ⏯️ 暂停 / 继续（启动请用主窗口按钮或悬浮窗右键菜单） |
| `8` | ➕ 手动 +1 污染 |
| `9` | ➖ 手动 -1 污染 |
| `-` | 🔒 锁定 / 解锁悬浮窗 |

> 全部热键都能在主窗口 **设置** 页自定义，支持小键盘（如 `num+`、`numpad7`）。

---

## 🚀 快速上手 · Quickstart

1. 🖱️ 启动程序（首次会自动请求管理员权限）。
2. ⚙️ 打开 **设置** → 选择与你屏幕匹配的分辨率预设（常用：`2560x1600_150缩放`）。
3. ▶️ 点 **开始监测** — 游戏里触发一次世界污染事件，悬浮窗会自动 +1。
4. 🔒 点 **锁定** — 悬浮窗变为点击穿透，不影响游戏操作。
5. 📊 **统计** 页查看今日 / 历史数据，支持手动修改、导入旧版 `pollution_count.json`。

---

## 🧩 OCR 误识别修复 · OCR Alias

程序默认自带一条别名修复：

```json
"ocr_name_aliases": {
  "噬光嗡嗡": "曙光瑜瑜"
}
```

想追加 / 修改？打开 exe 同级目录下的 `pollution_config.json`，编辑 `ocr_name_aliases` 字段即可。

---

## 🛠️ 从源码运行 · From Source

```powershell
# 1) 安装依赖
py -m pip install -r requirements.txt

# 2) 运行
py run_app.py

# 3) 打包（可选）
.\打包_新版.bat
```

需要 **Python 3.10+** 和 Windows。首次运行 PaddleOCR 会加载本地模型目录 `paddleocr_models`。

---

## 🩺 启动诊断 · Startup Diagnostics

其他电脑上"双击没反应"几乎总是以下几种原因之一：

- 🧱 缺 VC++ 运行库 → 装 `vc_redist.x64.exe`
- 🛡️ 杀毒软件拦截 → 加白名单
- 📁 解压路径含特殊字符 / 只读 → 换个正常目录
- 💥 PyQt6 / PaddleOCR 原生库加载失败 → 看下面这个日志

v1.2.3 起，任何启动阶段的异常都会自动写入 **`startup_error.log`**（exe 同级目录），包含 Python 版本、traceback、faulthandler 原生堆栈。把这个文件发给作者即可远程定位。

---

## ⚠️ 注意事项 · Notes

- 🔐 为保证全局热键、截屏识别、悬浮窗穿透生效，请 **以管理员身份运行**。
- 🖼️ OCR 不准？先检查 **设置 → 分辨率** 是否和实际一致。
- 🎯 程序只能隐藏 **系统光标**，无法隐藏游戏自绘光标。
- ♻️ 升级后如果旧配置覆盖了新默认值，可手动删除 `pollution_config.json` 让程序重建。

---

## 📝 更新日志 · Changelog

### 🆕 v1.2.3

- 🩺 **启动诊断**：崩溃时自动写 `startup_error.log`，含 `faulthandler` 原生堆栈
- 🧩 **OCR 别名表**：默认修复「噬光嗡嗡 → 曙光瑜瑜」，可自定义
- ➕ **手动 ± 零门槛**：没有当前精灵时自动回退到今日 / 累计榜首，实在没有会弹输入框让你挑
- ⌨️ **热键简化**：取消"启动"键，单键改为 ⏯️ 暂停 / 继续
- 👤 **关于页** 加作者信息：小丑鱼 · 抖音号 `conflicto834`

### v1.2.2

- 🔧 修复窗口化时识别不到的问题，恢复窗口偏移叠加与游戏窗口自动识别
- 🔧 优化热键兼容性，补充小键盘按键别名
- 🟡 新增暂停状态显示：悬浮窗 / 主窗口会变成黄灯并显示"已暂停"
- 📥 设置页新增旧版 count 文件导入（自动备份当前数据）

### v1.2.0

- 🐛 修复同场战斗被重复计数：加入触发沿检测
- ⏱️ 自动识别冷却 8 → 12 秒（手动 ± 不受影响）
- 🚀 UI 线程磁盘写入节流 2 秒，OCR 就绪后停止状态轮询

### v1.1.1

- 🐛 修复运行时鼠标卡顿：移除 `keyboard` 全局钩子，改用 Win32 `GetAsyncKeyState` 轮询
- 🐛 修复中文路径下 PaddleOCR 模型加载失败：自动复制模型到纯 ASCII 临时目录
- 🖼️ 小窗精灵统计列表根据条目数自动变长

> 📚 完整记录请看 [Releases 页面](https://github.com/YUZE04/Roco-pollution-counter/releases)。

---

## 👤 作者 · Author

<div align="center">

**小丑鱼** · 抖音号 [`conflicto834`](https://www.douyin.com/)

觉得好用？点个 ⭐ Star 支持一下！有 bug / 建议欢迎提 [Issue](https://github.com/YUZE04/Roco-pollution-counter/issues)。

</div>

---

## 📜 License

[AGPL-3.0](./LICENSE)
