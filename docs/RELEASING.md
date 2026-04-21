# Releasing

这个文档描述仓库的通用发布流程，不绑定某一个具体版本号。

## 1. 更新版本信息

- 更新 `app/__init__.py` 中的 `APP_VERSION`
- 同步检查 `app/backend/config.py` 默认 `app_version`
- 更新 `version.json` 的版本号、标题、说明和下载链接

## 2. 运行基础检查

```powershell
py -m compileall app tests
py -m py_compile 1.py
```

如果涉及打包链路或启动兼容性，建议额外手测：

- 首次启动是否能自动生成 `pollution_config.json` / `pollution_count.json`
- 中文路径下启动是否正常
- 主要热键是否正常

## 3. 本地打包

```powershell
py -m PyInstaller --noconfirm --clean "污染计数器v1.2.spec"
```

预期产物：

- `dist/污染计数器vX.Y.Z/污染计数器vX.Y.Z.exe`

如果需要 zip：

```powershell
Compress-Archive -Path "dist\污染计数器vX.Y.Z\*" -DestinationPath "污染计数器vX.Y.Z.zip" -CompressionLevel Optimal
```

## 4. 发布到 GitHub

1. 推送代码和标签
2. 在 GitHub Releases 创建对应版本
3. 上传 zip 或安装包附件
4. 确认 `version.json` 的下载地址与 Release 一致

## 5. 可选镜像

如果要提供国内镜像或其他下载渠道：

- 更新 `version.json` 里的镜像地址字段
- 确认 README 的下载说明与实际渠道一致

## 6. 发布后回归检查

- 从 GitHub Release 下载一份全新包
- 在干净目录解压并启动
- 验证更新检查、热键、OCR 初始化、中文路径兼容
