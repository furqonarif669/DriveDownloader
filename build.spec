# -*- mode: python ; coding: utf-8 -*-

import sys
import os
import platform

block_cipher = None

# OS Detection
system = platform.system()
is_windows = system == "Windows"
is_mac = system == "Darwin"

# We do NOT bundle binaries anymore because the app downloads them.
added_files = []

# Mac Specific: Ensure PySide6 dynamic libraries are found
# Usually PyInstaller handles this, but explicit hidden imports help.
hidden_imports = ['requests', 'PySide6']

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='DriveDownloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False, # DISABLE UPX FOR MAC STABILITY
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False, 
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    argv_emulation=False,
)

# Mac OS .app Bundle Configuration
if is_mac:
    app = BUNDLE(
        exe,
        name='DriveDownloader.app',
        icon=None,
        bundle_identifier='com.yourname.drivedownloader',
        info_plist={
            'NSHighResolutionCapable': 'True',
            'CFBundleShortVersionString': '1.0.0',
            'CFBundleVersion': '1.0.0',
            'CFBundleDisplayName': 'Drive Downloader',
            'CFBundleName': 'Drive Downloader',
            'CFBundlePackageType': 'APPL',
            'CFBundleExecutable': 'DriveDownloader', 
            'LSBackgroundOnly': 'False'
        }
    )