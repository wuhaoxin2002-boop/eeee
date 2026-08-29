# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for package in ('ddddocr', 'onnxruntime', 'cv2', 'PySide6'):
    d, b, h = collect_all(package)
    datas += d; binaries += b; hiddenimports += h

a = Analysis(['cuiqiu_qt.py'], pathex=['.'], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, excludes=['tkinter'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='CuiqiuCaptcha',
          debug=False, bootloader_ignore_signals=False, strip=False,
          upx=False, console=True)
