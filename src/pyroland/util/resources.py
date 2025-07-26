"""
Resource helpers for files bundled via importlib.resources.

Example
-------
from pyroland.util.resources import data_path
csv = data_path("camera_quantum_efficiency.csv")
"""
from importlib.resources import files
from pathlib import Path

_DATA_PACKAGE = "pyroland.corrections.data"
_ICON_PACKAGE = "pyroland.icons"


def data_path(filename: str) -> Path:
    """
    Return a *Path* to a data file located in ``pyroland/corrections/data``.

    Works transparently whether the package lives on the filesystem,
    inside a wheel, or extracted by PyInstaller.
    """
    return files(_DATA_PACKAGE).joinpath(filename)

def icon_path(name: str = "app.ico") -> Path:
    return files(_ICON_PACKAGE).joinpath(name)
