# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Pyroland GUI application.
Bundles the PySide6 runtime, Qt .ui files, images, and CSV data into a single executable.
"""
import os

# Collect all PySide6 dependencies
from PyInstaller.utils.hooks import collect_all
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT

datas, binaries, hiddenimports = collect_all('PySide6')

# Helper to include entire directories of data files
def collect_dir(src_dir, dest_prefix):
    """
    Walk `src_dir` and return a list of (src_path, dest_folder) tuples
    for PyInstaller's datas.
    """
    data_items = []
    for root, dirs, files in os.walk(src_dir):
        for fname in files:
            src_path = os.path.join(root, fname)
            rel_root = os.path.relpath(root, src_dir)
            # If at top level, avoid leading './' in dest folder
            if rel_root in (".", ""):
                dest_folder = dest_prefix
            else:
                dest_folder = os.path.join(dest_prefix, rel_root)
            data_items.append((src_path, dest_folder))
    return data_items

# Include Qt .ui files
datas += collect_dir(
    os.path.join('src', 'pyroland', 'gui', 'ui'),
    os.path.join('pyroland', 'gui', 'ui')
)
# Include correction images
datas += collect_dir(
    os.path.join('src', 'pyroland', 'resources', 'corrections'),
    os.path.join('pyroland', 'resources', 'corrections')
)
# Include CSV data files
datas += collect_dir(
    os.path.join('src', 'pyroland', 'corrections', 'data'),
    os.path.join('pyroland', 'corrections', 'data')
)

# No encryption
block_cipher = None

# Analyze and collect dependencies
a = Analysis(
    ['src/pyroland/main.py'],          # Entry-point script
    pathex=[os.path.abspath('.')],    # Project root
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)

# Create a Python module archive (PYZ)
pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

# Build the executable
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='pyroland',                   # Executable name
    debug=False,
    strip=False,
    upx=True,
    console=False,                     # GUI app
    icon=os.path.join('src', 'pyroland', 'icons', 'app.ico'),
)

# (Optional) Collect into a single folder (not needed for --onefile builds)
collect = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='pyroland_dist',
)
