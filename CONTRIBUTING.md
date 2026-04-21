# Contributing

感谢你愿意改进污染计数器。

## 开始之前

- 建议先开一个 issue，描述你想修的问题或想加的功能。
- 本项目当前优先接收：启动稳定性、OCR 兼容性、热键、窗口识别、文档改进。
- 较大的 UI 重构或架构调整，最好先讨论再开工。

## 本地开发

```powershell
py -m pip install -r requirements.txt
py run_app.py
```

- 仓库里提交的是 `pollution_config.example.json` 和 `pollution_count.example.json`。
- 真正运行时生成的 `pollution_config.json`、`pollution_count.json`、`dist/`、`build/` 都不要提交。
- `paddleocr_models/` 体积较大，默认不进 Git；源码运行前请先准备本地模型目录。

## 提交前检查

```powershell
py -m compileall app
py -m py_compile 1.py
```

- 如果你改了打包链路，最好额外跑一次 PyInstaller 构建。
- 如果你修的是“启动失败”问题，请附上复现方式，以及 `startup_error.log` 的关键片段。

## Pull Request 建议

- 标题尽量具体，例如：`fix: avoid duplicate show_main hotkey migration`
- 描述里请写清楚：
  - 改了什么
  - 为什么改
  - 怎么验证的

## 行为约定

- 不要提交本地构建产物、日志、统计数据、网盘凭证或个人配置。
- 尽量保持中文 UI 文案统一、直接、可理解。
- 如果修改了用户可见行为，请同步更新 README 或相关文档。
