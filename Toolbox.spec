# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Toolbox (PySide6 desktop app)
# Build: python -m PyInstaller Toolbox.spec
#
# Map display in the exe requires QtWebEngine. Install it in the build environment:
#   pip install pyside6-addons
# Then rebuild. Without it, the exe will show "Map module not available".

from PyInstaller.utils.hooks import collect_all

# Collect PySide6 (full collect ensures QtWebEngine and all dependencies are included)
pyside6_datas, pyside6_binaries, pyside6_hiddenimports = collect_all('PySide6')

# Filter out only obvious bloat; keep all WebEngine-related and runtime-needed files
filtered_datas = []
for data in pyside6_datas:
    src, dst = data
    src_lower = src.lower()
    # Exclude examples, tests, demos, tutorials (not needed at runtime)
    if any(x in src_lower for x in ['/example', '\\example', '/test', '\\test', '/demo', '\\demo', 'tutorial', 'sample']):
        continue
    # Keep translations, docs, and everything else (WebEngine may need resources)
    filtered_datas.append(data)

# Exclude unnecessary PySide6 modules to reduce size significantly
excludes = [
    # 3D modules (not used)
    'PySide6.Qt3DAnimation',
    'PySide6.Qt3DCore',
    'PySide6.Qt3DExtras',
    'PySide6.Qt3DInput',
    'PySide6.Qt3DLogic',
    'PySide6.Qt3DRender',
    # Bluetooth (not used)
    'PySide6.QtBluetooth',
    # Charts (not used)
    'PySide6.QtCharts',
    # Data visualization (not used)
    'PySide6.QtDataVisualization',
    # Designer tools (not used)
    'PySide6.QtDesigner',
    # Help system (not used)
    'PySide6.QtHelp',
    # Location services (not used)
    'PySide6.QtLocation',
    # Multimedia (not used)
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',
    # NFC (not used)
    'PySide6.QtNfc',
    # OpenGL (not used)
    'PySide6.QtOpenGL',
    'PySide6.QtOpenGLWidgets',
    # Positioning (not used)
    'PySide6.QtPositioning',
    # QML/Quick (not used - we use widgets)
    'PySide6.QtQml',
    'PySide6.QtQuick',
    'PySide6.QtQuick3D',
    'PySide6.QtQuickControls2',
    'PySide6.QtQuickWidgets',
    # Remote objects (not used)
    'PySide6.QtRemoteObjects',
    # Sensors (not used)
    'PySide6.QtSensors',
    # Serial port (not used)
    'PySide6.QtSerialPort',
    # SQL (not used)
    'PySide6.QtSql',
    # State machine (not used)
    'PySide6.QtStateMachine',
    # Test framework (not needed in exe)
    'PySide6.QtTest',
    # Text to speech (not used)
    'PySide6.QtTextToSpeech',
    # UI tools (not used)
    'PySide6.QtUiTools',
    # WebSockets (not used)
    'PySide6.QtWebSockets',
    # XML (not used)
    'PySide6.QtXml',
    'PySide6.QtXmlPatterns',
    # Development/testing tools
    'pytest',
    'unittest',
    'test',
    'tests',
    'IPython',
    'jupyter',
    'notebook',
    # Pandas optional dependencies we don't need
    'matplotlib',
    'scipy',
    'scikit-learn',
    'statsmodels',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=pyside6_binaries,
    datas=[
        ('map_template_google.html', '.'),
        ('config.example.json', '.'),
        ('config.json.template', 'config.json'),  # Include as config.json in build
        ('icons', 'icons'),
    ] + filtered_datas,
    hiddenimports=[
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebChannel',  # used by WebEngine
        'PySide6.QtSvg',
        'PySide6.QtNetwork',    # used by WebEngine
    ] + pyside6_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
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
