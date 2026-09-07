# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('C:\\CODE300725\\.git', '.git/'), ('C:\\CODE300725\\Alpha_Image', 'Alpha_Image/'), ('C:\\CODE300725\\Batch', 'Batch/'), ('C:\\CODE300725\\Captured_Img_LCD', 'Captured_Img_LCD/'), ('C:\\CODE300725\\Captured_Img_LED', 'Captured_Img_LED/'), ('C:\\CODE300725\\config_files', 'config_files/'), ('C:\\CODE300725\\Failed_images', 'Failed_images/'), ('C:\\CODE300725\\general', 'general/'), ('C:\\CODE300725\\models', 'models/'), ('C:\\CODE300725\\resources', 'resources/'), ('C:\\CODE300725\\template', 'template/'), ('C:\\CODE300725\\yolov5', 'yolov5/'), ('C:\\CODE300725\\.gitignore', '.'), ('C:\\CODE300725\\generate_report.py', '.'), ('C:\\CODE300725\\inference_report.csv', '.'), ('C:\\CODE300725\\pyqt5_app.py', '.'), ('C:\\CODE300725\\requirements.txt.txt', '.')]
binaries = []
hiddenimports = ['onnx', 'onnxruntime']
tmp_ret = collect_all('ultralytics')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['C:\\CODE300725\\pyqt5_app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DisplayUtilityV2.00',
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
    icon=['C:\\CODE300725\\resources\\splash_img.ico'],
    contents_directory='data',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DisplayUtilityV2.00',
)
