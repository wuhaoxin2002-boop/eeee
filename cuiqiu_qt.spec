# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

# ddddocr keeps its ONNX model beside the package. Native dependencies are
# discovered by PyInstaller's standard hooks from the modules actually used.
datas = collect_data_files('ddddocr')

a = Analysis(['cuiqiu_qt.py'], pathex=['.'], binaries=[], datas=datas,
             hiddenimports=[], excludes=[
                 'tkinter', 'PySide6.QtWebEngineCore',
                 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick',
                 'PySide6.QtQml', 'PySide6.QtQuick',
                 'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
             ], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='CuiqiuCaptcha',
          debug=False, bootloader_ignore_signals=False, strip=False,
          upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
               name='CuiqiuCaptcha')
