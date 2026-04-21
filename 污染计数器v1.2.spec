# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the PyQt6-rewritten app (app/main.py).

Packages:
  - app/ package source tree
  - 1.py  (动态加载用：app/backend/ocr.py 在运行时会把它当成 legacy 模块)
  - paddleocr_models  目录
  - 图标 / 配置

Output: dist/污染计数器v1.2.5/ 下会有 污染计数器v1.2.5.exe
"""

from PyInstaller.utils.hooks import collect_all


# ---------- 数据 & 二进制 ----------

datas = [
    ('app', 'app'),                              # 整个包复制进去
    ('1.py', '.'),                               # OCR 动态加载用
    ('paddleocr_models', 'paddleocr_models'),    # OCR 模型
    ('roco_counter_icon.ico', '.'),
    ('pollution_config.example.json', '.'),
    ('pollution_count.example.json', '.'),
    ('version.json', '.'),
]

binaries = []

# PyQt6 + PaddleOCR 都要 collect_all，以便 hidden import / 子模块完整
hiddenimports = [
    # 动态加载的 OCR 依赖
    'imagesize', 'pyclipper', 'pypdfium2', 'bidi.algorithm', 'shapely',
    'filelock', 'ruamel.yaml',
    # 旧版 1.py 的运行时依赖（被 app/backend/ocr.py 动态加载，PyInstaller 静态
    # 分析抓不到）
    'keyboard', 'mss', 'cv2', 'numpy', 'yaml',
    'tkinter', 'tkinter.messagebox', 'tkinter.scrolledtext', 'tkinter.font',
    # PyQt6（Analysis 通常会自动抓到，但以防万一）
    'PyQt6.sip', 'PyQt6.QtGui', 'PyQt6.QtCore', 'PyQt6.QtWidgets',
]

for _pkg in ('paddle', 'paddleocr', 'paddlex', 'ruamel.yaml'):
    _datas, _bins, _imports = collect_all(_pkg)
    datas += _datas
    binaries += _bins
    hiddenimports += _imports


# ---------- 分析 ----------

a = Analysis(
    ['run_app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch', 'torchvision', 'torchaudio',
        'tensorboard', 'tensorflow',
        'jax', 'jaxlib',
        'langchain', 'langchain_core', 'langchain_text_splitters',
        # 注意：不要 exclude tkinter —— 1.py 会用到它
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='污染计数器v1.2.5',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,
    icon=['roco_counter_icon.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='污染计数器v1.2.5',
)
