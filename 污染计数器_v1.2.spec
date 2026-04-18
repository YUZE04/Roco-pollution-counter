# -*- mode: python ; coding: utf-8 -*-
"""v1.2.0 PyQt6 重写版打包配置。
入口是 app/main.py；同时把旧版 1.py 作为数据文件带上（OCR 代码动态导入）。"""

from PyInstaller.utils.hooks import collect_all

datas = [
    ('paddleocr_models', 'paddleocr_models'),
    ('roco_counter_icon.ico', '.'),
    ('1.py', '.'),  # 新版 OCR 通过 importlib.util 动态加载 1.py
]
binaries = []
hiddenimports = [
    'imagesize', 'pyclipper', 'pypdfium2', 'bidi.algorithm',
    'shapely', 'filelock', 'ruamel.yaml',
    'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
]
for mod in ('paddle', 'paddleocr', 'paddlex', 'ruamel.yaml'):
    _d, _b, _h = collect_all(mod)
    datas += _d
    binaries += _b
    hiddenimports += _h


a = Analysis(
    ['app/main.py'],
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
        # 不能排除 tkinter：旧版 1.py 仍在以模块形式被动态导入以复用 OCR 代码
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
    name='污染计数器v1.2.0',
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
    icon=['roco_counter_icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='污染计数器v1.2.0',
)
