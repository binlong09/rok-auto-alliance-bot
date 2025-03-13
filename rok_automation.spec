# -*- mode: python ; coding: utf-8 -*-

import os

block_cipher = None

# Define your project directory structure directly
SRC_DIR = 'src'

a = Analysis(
    [os.path.join(SRC_DIR, 'main.py')],  # Path to your main script in src/ directory
    pathex=[SRC_DIR],                     # Add src/ to the path
    binaries=[],
    datas=[
        (os.path.join(SRC_DIR, 'config.ini'), '.'),  # Config file from src directory
        # Add any additional data files
        # ('assets/*', 'assets'),  # Uncomment if you have an assets folder
    ],
    hiddenimports=[
        'PIL._tkinter_finder',
        'cv2',
        'numpy',
        'configparser',
        'pytesseract',
    ],
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
    [],
    exclude_binaries=True,
    name='RoK Automation',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/rok_icon.ico' if os.path.exists('assets/rok_icon.ico') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RoK Automation',
)