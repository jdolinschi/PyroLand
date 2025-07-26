# pyroland.spec  – minimal, one-file build
block_cipher = None

a = Analysis(
    ["src/pyroland/main.py"],
    pathex=[],
    datas=[
        ("src/pyroland/corrections/data/*.csv", "pyroland/corrections/data"),
        ("src/pyroland/resources/**/*",          "pyroland/resources"),
        ("src/pyroland/gui/ui/*.ui",             "pyroland/gui/ui"),
        ("src/pyroland/icons/app.ico",           "pyroland/icons"),
    ],
    hiddenimports=["PySide6.QtSvg"],  # add more if PyInstaller complains
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,    # ← these three lists are essential
    a.zipfiles,
    a.datas,
    name="Pyroland",
    icon="src/pyroland/icons/app.ico",
    console=False,
    onefile=True,
)
