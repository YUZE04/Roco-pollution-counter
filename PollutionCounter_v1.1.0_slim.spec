# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('paddleocr_models', 'paddleocr_models'), ('roco_counter_icon.ico', '.'), ('version.json', '.'), ('ocr_capture_positions.json', '.')]
binaries = []
hiddenimports = ['paddlex', 'paddlex.inference', 'paddlex.utils.device', 'paddlex.utils.flags', 'paddlex.utils.logging', 'paddlex.utils.deps', 'paddlex.inference.utils.benchmark', 'cv2', 'imagesize', 'pyclipper', 'pypdfium2', 'bidi', 'shapely']
tmp_ret = collect_all('paddleocr')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('paddlex')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['pollution_counter.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'torchvision', 'modelscope', 'tensorflow', 'matplotlib', 'pyarrow'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PollutionCounter_v1.1.0_slim',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    upx=True,
    upx_exclude=[],
    name='PollutionCounter_v1.1.0_slim',
)
