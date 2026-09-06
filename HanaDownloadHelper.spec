# -*- mode: python ; coding: utf-8 -*-
# ============================================================
#  PyInstaller 打包配置（onedir 模式：小 exe + 同目录 dll）
#  构建： pyinstaller HanaDownloadHelper.spec
#  产物： dist/HanaDownloadHelper/HanaDownloadHelper.exe  + 一堆 dll
# ============================================================

import sys

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    # libtorrent / requests 在代码中是“函数内延迟 import”，静态分析抓不到，必须显式声明
    hiddenimports=[
        "libtorrent",
        "requests",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtNetwork",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HanaDownloadHelper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,                 # GUI 程序，不弹黑框
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="HanaDownloadHelper",
)
