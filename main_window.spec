# main_window.spec

# This is a PyInstaller spec file. It tells PyInstaller how to build your application.
# To use it, run: pyinstaller main_window.spec

import sys
import os

# Get the directory of the spec file
base_dir = os.path.dirname(os.path.abspath(__file__))

# --- Data files to be included ---
# List of tuples: (source_path, destination_in_bundle)
# '.' for destination means the root of the bundle, alongside the executable.
datas = [
    ('exchange_variables.csv', '.'),
    ('snap7_node_ids.json', '.'),
    ('database.py', '.'),
    ('plc_simulator.py', '.')
]

# --- Native binaries to be included ---
binaries = [
    ('snap7.dll', '.')
]

a = Analysis(
    ['main_window.py'],
    pathex=[base_dir],
    binaries=binaries,
    datas=datas,
    hiddenimports=['pyqtgraph.graphicsItems.ViewBox.axisCtrlTemplate_pyqt5'], # Common hidden import for pyqtgraph
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ProAutomation Studio', # The name of your executable
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False, # Set to False for GUI applications to hide the console window
    icon=None, # You can specify a path to a .ico file here
    upx_exclude=[],
    runtime_tmpdir=None,
    version=None,
    uac_admin=False,
    manifest=None
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ProAutomationApp' # The name of the output folder in 'dist'
)
