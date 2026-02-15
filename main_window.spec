# main_window.spec
#
# PyInstaller spec file for DecAutomation Studio.
# Bundles the full application with onboarding dashboard, monitoring sub-app
# (monitoring/external/), and data files so it runs on PCs without Python,
# TwinCAT, or any other runtime pre-installed.
#
# Usage:  pyinstaller main_window.spec

import sys
import os

# ── paths ────────────────────────────────────────────────────────────
# SPECPATH is injected by PyInstaller – it points to the folder containing this .spec file
base_dir = SPECPATH
monitoring_dir = os.path.join(base_dir, 'monitoring')
step7_dir = os.path.join(base_dir, 'step7_exchange')
st_block_dir = os.path.join(base_dir, 'st_block')
hmi_plc_dir = os.path.join(base_dir, 'hmi_plc')
block_station_dir = os.path.join(base_dir, 'block_station_generator')
images_dir = os.path.join(base_dir, 'Images')
icon_file = os.path.join(images_dir, 'app_icon.ico')

# ── version (read from version.txt) ─────────────────────────────────
_ver_file = os.path.join(base_dir, 'version.txt')
APP_VERSION = open(_ver_file).read().strip() if os.path.isfile(_ver_file) else '1.0.0'

# ── data files to bundle ─────────────────────────────────────────────
# Tuple format:  (source_path, destination_folder_in_bundle)
# '.' = bundle root  |  'external' = <bundle>/external/  etc.
datas = [
    # ── Images ───────────────────────────────────────────────────────
    (os.path.join(images_dir, 'Dec Group_bleu_noir_transparent.png'), 'Images'),
    (os.path.join(images_dir, 'Dec True end-to-end final white_small.png'), 'Images'),
    (os.path.join(images_dir, 'dec_background_endToEnd_bottomRight.png'), 'Images'),
    (os.path.join(images_dir, 'DEC_G-2016_WHITE.png'), 'Images'),
    (os.path.join(images_dir, 'app_icon.ico'), 'Images'),
] + [(p, 'Images') for p in [
    os.path.join(images_dir, 'DEC_Monitoring.png'),
    os.path.join(images_dir, 'DEC_Exchange.png'),
    os.path.join(images_dir, 'DEC_S_T_BlockConfig.png'),
    os.path.join(images_dir, 'DEC_HMI_PLC.png'),
    os.path.join(images_dir, 'DEC_BlockStation.png'),
] if os.path.isfile(p)] + [
    # ── Shared UI (CustomTitleBar, get_app_icon) ───────────────────────
    (os.path.join(base_dir, 'shared'), 'shared'),

    # ── Sub-applications (config files are inside monitoring/external/) ─
    (monitoring_dir, 'monitoring'),
    (step7_dir, 'step7_exchange'),
    (st_block_dir, 'st_block'),
    (hmi_plc_dir, 'hmi_plc'),
    (os.path.join(hmi_plc_dir, 'projects'), 'hmi_plc/projects'),
    (block_station_dir, 'block_station_generator'),

    # ── Onboarding assets (tile images) ───────────────────────────────
    (os.path.join(base_dir, 'onboarding', 'assets'), 'onboarding/assets'),
]

# ── native binaries ──────────────────────────────────────────────────
binaries = [
    (os.path.join(base_dir, 'snap7.dll'), '.'),
]

# ── hidden imports ───────────────────────────────────────────────────
# Libraries that PyInstaller's static analysis may miss.
hidden_imports = [
    # pyqtgraph internal templates
    'pyqtgraph.graphicsItems.ViewBox.axisCtrlTemplate_pyqt5',
    'pyqtgraph.graphicsItems.ViewBox.axisCtrlTemplate_pyside6',
    'pyqtgraph.graphicsItems.PlotItem.plotConfigTemplate_pyqt5',
    'pyqtgraph.graphicsItems.PlotItem.plotConfigTemplate_pyside6',
    # PySide6 backends
    'PySide6.QtSvg',
    'PySide6.QtPrintSupport',
    # duckdb
    'duckdb',
    # numeric / scientific
    'numpy',
    'scipy',
    'scipy.signal',
    'scipy.interpolate',
    # communication
    'snap7',
    'snap7.client',
    'snap7.util',
    'pyads',
    # web / analytics (Dash + Flask)
    'flask',
    'flask_cors',
    'waitress',
    'dash',
    'dash.dependencies',
    'plotly',
    'plotly.graph_objects',
    'plotly.express',
    'pandas',
    'matplotlib',
    # shared UI (title bar, app icon)
    'shared',
    'shared.title_bar',
    # monitoring sub-app (external = monitoring/external when pathex includes monitoring)
    'monitoring.main_window',
    'external',
    'external.plc_thread',
    'external.plc_ads_thread',
    'external.plc_simulator',
    'external.variable_loader',
    'external.analytics_window',
    'external.calculations',
    'external.database',
    # hmi_plc sub-app
    'hmi_plc.main',
    'hmi_plc.main_window',
    'hmi_plc.requests_loader',
    'hmi_plc.hmi_components',
    'hmi_plc.hmi_canvas_widget',
    'hmi_plc.block_component',
    'hmi_plc.block_definitions',
    'hmi_plc.fc_generator',
    'hmi_plc.simulation',
    'hmi_plc.simulation_config_widget',
    # misc
    'psutil',
    'json',
    'csv',
    'logging',
    'collections',
]

# ── Analysis ─────────────────────────────────────────────────────────
a = Analysis(
    ['main.py'],                         # entry point
    pathex=[monitoring_dir, base_dir],   # monitoring first so 'external' -> monitoring/external
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        'tkinter', '_tkinter',           # not used – save space
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# ── Build objects ────────────────────────────────────────────────────
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DecAutomation Studio',         # executable name
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,                       # GUI app – no console window
    icon=icon_file if os.path.isfile(icon_file) else None,
    upx_exclude=[],
    runtime_tmpdir=None,
    version=None,
    uac_admin=False,
    manifest=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DecAutomationApp',             # output folder: dist/DecAutomationApp/
)
