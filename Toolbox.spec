# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Toolbox (PySide6 desktop app)
# Build: pyinstaller Toolbox.spec

from PyInstaller.utils.hooks import collect_all

pyside6_datas, pyside6_binaries, pyside6_hiddenimports = collect_all('PySide6')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=pyside6_binaries,
    datas=[
        ('map_template_google.html', '.'),
        ('config.example.json', '.'),
        ('icons', 'icons'),
    ] + pyside6_datas,
    hiddenimports=[
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineCore',
        'PySide6.QtSvg',
    ] + pyside6_hiddenimports,
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
    name='Toolbox',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Toolbox',
)
