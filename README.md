# Roco Kingdom World Pollution Counter

一个用于洛克王国世界污染追踪的桌面计数工具。  
A desktop counter tool for Roco Kingdom world pollution tracking.
下载地址：https://github.com/YUZE04/Roco-pollution-counter/archive/refs/tags/v1.1.0.zip
---

## 简介 | Introduction

本工具用于在游戏过程中记录污染次数，并通过悬浮窗方式显示当前统计结果。  
它适合需要边玩边看统计信息的场景，支持热键操作、紧凑悬浮窗显示、每日数据记录与物种统计等功能。

This tool is designed to record pollution counts during gameplay and display the results in a floating window.  
It is suitable for players who want to track data while playing, with support for hotkeys, compact floating mode, daily statistics, and species statistics.

---

## 功能特性 | Features

- OCR 文本识别  
  OCR text recognition

- 自动计数  
  Automatic counting

- 手动热键加减  
  Manual hotkey add and subtract

- 无边框紧凑悬浮窗  
  Borderless compact floating window

- 锁定后整窗鼠标穿透  
  Full-window mouse passthrough when locked

- 锁定后隐藏系统光标  
  Hide system cursor when locked

- 分辨率切换  
  Resolution switching

- 150% 缩放预设支持  
  150% scaling preset support

- 每日统计数据  
  Daily statistics

- 精灵统计总表  
  Species statistics summary

- GitHub 更新检查  
  GitHub update checking

---

## 默认热键 | Default Hotkeys

- 启动 / 关闭：`7`
- 增加污染：`8`
- 减少污染：`9`
- 暂停：`0`
- 锁定 / 移动：`-`

---

## 使用说明 | How to Use

1. 启动程序后，先进入 **设置** 检查当前分辨率。  
2. 选择与你当前屏幕一致的预设。  
3. 使用默认热键启动识别。  
4. 锁定后，悬浮窗会进入更适合游戏界面的显示状态。  
5. 统计数据可在详情页中查看和保存。

1. After launching the program, open **Settings** and check the current resolution preset.  
2. Select the preset that matches your screen.  
3. Use the default hotkeys to start detection.  
4. When locked, the floating window enters a more game-friendly overlay mode.  
5. Statistics can be viewed and saved in the details page.

---

## 运行环境 | Requirements

- Windows
- Python 3.10+
- 建议使用管理员身份运行  
  Administrator mode is recommended

---

## 注意事项 | Notes

- 为保证全局热键、截屏识别和悬浮窗效果正常，建议以管理员身份运行。  
- 如果首次使用识别不准确，请先检查分辨率设置是否正确。  
- 如果游戏使用自绘光标，程序只能隐藏系统光标，无法隐藏游戏内部绘制的光标。  
- 若已存在旧配置文件，部分默认热键和界面设置可能不会立即更新。

- To ensure hotkeys, screen capture, and floating window features work properly, it is recommended to run the program as administrator.  
- If OCR is inaccurate on first use, check whether the resolution preset is correct.  
- If the game uses a custom in-game cursor, the program can only hide the system cursor, not the in-game drawn cursor.  
- If an old config file already exists, some default hotkeys and UI settings may not update immediately.

---

## 更新日志 | Changelog

当前正式版本：`v1.1.0`

- 修复 PaddleOCR 在 CPU 环境下的兼容问题
- 优化紧凑悬浮窗布局、锁定交互与提示文案
- 增强分辨率预设适配，支持按当前分辨率自动推算区域
- 降低待机扫描时的空转 CPU 占用

详细更新内容请查看 Release 页面。  
For detailed updates, please check the Release page.

---

## License

AGPL-3.0
