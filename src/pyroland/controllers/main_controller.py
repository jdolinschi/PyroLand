# file: src/pyroland/controllers/maincontroller.py
"""
maincontroller.py

High-level controller that wires the Qt UI to application logic:
* Folder selection & live directory watching.
* Table view of all `.sif` files (newest → oldest).
* Delegates plotting to :class:`~src.pyroland.controllers.plot_controller.PlotController`.

Updated to use **sif-parser** (`sif_parser.utils.parse`) instead of the
non-existent `SifFile` class.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import List, Tuple

import numpy as np
from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QTableWidgetItem
from sif_parser.utils import parse as sif_parse  # <-- correct import

from src.pyroland.controllers.plot_controller import PlotController

__all__ = ["MainController"]


# --------------------------------------------------------------------------- #
#                               Worker Thread                                 #
# --------------------------------------------------------------------------- #
class DirectoryWatcher(QThread):
    """
    Poll *directory* for `.sif` files and emit an updated list whenever the
    contents change.
    """
    files_changed = Signal(list)  # list[Path]

    def __init__(
        self,
        directory: Path,
        poll_interval: float = 2.0,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._directory = directory
        self._interval = poll_interval
        self._running = True
        self._known: set[Path] = set()

    # ---- QThread lifecycle ------------------------------------------- #
    def run(self) -> None:
        self._known = self._current_files()
        self.files_changed.emit(list(self._known))  # initial table fill

        while self._running:
            time.sleep(self._interval)
            now = self._current_files()
            if now != self._known:
                self._known = now
                self.files_changed.emit(list(now))

    def stop(self) -> None:
        self._running = False
        self.wait()

    # ---- Helpers ------------------------------------------------------ #
    def _current_files(self) -> set[Path]:
        return {p for p in self._directory.glob("*.sif") if p.is_file()}


# --------------------------------------------------------------------------- #
#                              Main Controller                                #
# --------------------------------------------------------------------------- #
class MainController(QObject):
    """All non-plot UI responsibilities are handled here."""

    def __init__(self, window) -> None:
        super().__init__(window)
        self.window = window
        self.ui = window.ui

        # Plot helper
        self._plot_manager = PlotController(self.ui.plot_widget)

        self._current_dir: Path | None = None
        self._watcher: DirectoryWatcher | None = None

        self._connect_signals()
        self._configure_table()

        QApplication.instance().aboutToQuit.connect(self._cleanup_threads)

    # ------------------------------------------------------------------ #
    # UI wiring
    # ------------------------------------------------------------------ #
    def _connect_signals(self) -> None:
        self.ui.folder_pushButton.clicked.connect(self._on_select_folder)

    def _configure_table(self) -> None:
        tbl = self.ui.tableWidget
        tbl.setColumnCount(1)
        tbl.setHorizontalHeaderLabels(["File name"])
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(tbl.EditTrigger.NoEditTriggers)
        tbl.setSelectionBehavior(tbl.SelectionBehavior.SelectRows)
        tbl.setSortingEnabled(False)
        tbl.itemDoubleClicked.connect(self._on_table_item_double_clicked)

    # ------------------------------------------------------------------ #
    # Folder selection
    # ------------------------------------------------------------------ #
    @Slot()
    def _on_select_folder(self) -> None:
        start = str(self._current_dir) if self._current_dir else os.getcwd()
        folder = QFileDialog.getExistingDirectory(
            parent=self.window,
            caption="Select folder to watch",
            dir=start,
            options=QFileDialog.Option.ShowDirsOnly,
        )
        if not folder:
            return

        folder_path = Path(folder)
        self.ui.folderwatching_label.setText(str(folder_path))
        self._start_watcher(folder_path)

    # ------------------------------------------------------------------ #
    # Directory watching
    # ------------------------------------------------------------------ #
    def _start_watcher(self, directory: Path) -> None:
        if self._watcher:
            self._watcher.files_changed.disconnect(self._on_files_changed)
            self._watcher.stop()

        self._current_dir = directory
        self._watcher = DirectoryWatcher(directory)
        self._watcher.files_changed.connect(self._on_files_changed)
        self._watcher.start()

    @Slot(list)
    def _on_files_changed(self, files: List[Path]) -> None:
        """Refresh table & plot newest spectrum whenever file set updates."""
        sorted_files = self._populate_table(files)
        if sorted_files:
            self._plot_file(sorted_files[0])

    # ------------------------------------------------------------------ #
    # Table population
    # ------------------------------------------------------------------ #
    def _populate_table(self, files: List[Path]) -> List[Path]:
        files.sort(key=lambda p: p.stat().st_ctime, reverse=True)

        tbl = self.ui.tableWidget
        tbl.setRowCount(len(files))

        for row, path in enumerate(files):
            item = QTableWidgetItem(path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            tbl.setItem(row, 0, item)

        tbl.resizeColumnsToContents()
        return files

    # ------------------------------------------------------------------ #
    # Plotting helpers
    # ------------------------------------------------------------------ #
    @Slot(QTableWidgetItem)
    def _on_table_item_double_clicked(self, item: QTableWidgetItem) -> None:
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        self._plot_file(path)

    def _plot_file(self, path: Path) -> None:
        try:
            wavelengths_nm, counts = self._read_sif(path)
        except Exception as err:
            print(f"[ERROR] Failed to read {path}: {err}")
            return

        if wavelengths_nm.size == 0 or counts.size == 0:
            return

        title = f"{path.name} — latest spectrum"
        self._plot_manager.plot_spectrum(wavelengths_nm, counts, title=title)

    # ---- SIF reader --------------------------------------------------- #
    @staticmethod
    def _read_sif(path: Path) -> Tuple[np.ndarray, np.ndarray]:
        """
        Use ``sif_parser.utils.parse`` to return *wavelengths_nm, counts*.

        The parser returns:
            data : (N×2) ndarray [[wavelength, counts], ...]
            info : OrderedDict (ignored here)

        Wavelength is already in nanometres.
        """
        data, _info = sif_parse(str(path))
        if data.ndim != 2 or data.shape[1] < 2:
            raise ValueError("Unexpected SIF data shape")

        wavelengths_nm = np.asarray(data[:, 0], dtype=float)
        counts = np.asarray(data[:, 1], dtype=float)
        return wavelengths_nm, counts

    # ------------------------------------------------------------------ #
    # Shutdown
    # ------------------------------------------------------------------ #
    @Slot()
    def _cleanup_threads(self) -> None:
        if self._watcher:
            self._watcher.stop()
            self._watcher = None
