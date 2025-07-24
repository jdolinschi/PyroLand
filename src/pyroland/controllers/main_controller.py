# file: src/pyroland/controllers/main_controller.py
"""
main_controller.py
==================

High-level Qt controller that connects the GUI to application logic.

This version adds support for two global X-range controls:

    • globalXMin_lineEdit  →  lower wavelength bound  [nm]
    • globalXMax_lineEdit  →  upper wavelength bound  [nm]

* Both accept floats/integers via a QDoubleValidator.
* Empty value → “no bound”.
* Editing-finished (enter key or focus-out) triggers re-plot.
* Invalid input pops up a warning and the value is discarded.
* The *fit* uses only the in-range data, while the plot shows out-of-range
  points in grey for clarity.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import List, Tuple, Optional

import numpy as np
from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QListWidgetItem,
    QTableWidgetItem,
    QMessageBox,
)

from sif_parser.utils import parse as sif_parse  # correct import

from src.pyroland.controllers.plot_controller import PlotController
from src.pyroland.controllers.corrections_controller import CorrectionsController
from src.pyroland.controllers.temperature_controller import TemperatureController

__all__ = ["MainController"]

# --------------------------------------------------------------------------- #
#                               Worker Thread                                 #
# --------------------------------------------------------------------------- #
class DirectoryWatcher(QThread):
    """Poll *directory* for ``.sif`` files and emit a list whenever it changes."""

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

    def run(self) -> None:
        self._known = self._current_files()
        self.files_changed.emit(list(self._known))  # initial populate
        while self._running:
            time.sleep(self._interval)
            now = self._current_files()
            if now != self._known:
                self._known = now
                self.files_changed.emit(list(now))

    def stop(self) -> None:
        self._running = False
        self.wait()

    def _current_files(self) -> set[Path]:
        return {p for p in self._directory.glob("*.sif") if p.is_file()}


# --------------------------------------------------------------------------- #
#                              Main Controller                                #
# --------------------------------------------------------------------------- #
class MainController(QObject):
    """All non-plot UI responsibilities are handled here."""

    _FIBER_LENGTH_M = 2.0  # default fibre length (m)

    def __init__(self, window) -> None:
        super().__init__(window)
        self.window = window
        self.ui = window.ui

        # Helper managers
        self._plot_manager = PlotController(self.ui.plot_widget)
        self._corr_manager = CorrectionsController(fiber_length_m=self._FIBER_LENGTH_M)
        self._temp_manager = TemperatureController()

        # Runtime state
        self._current_dir: Optional[Path] = None
        self._watcher: Optional[DirectoryWatcher] = None
        self._last_plot_path: Optional[Path] = None  # re-plot on correction toggle
        self._global_xmin: Optional[float] = None
        self._global_xmax: Optional[float] = None

        # GUI setup
        self._configure_table()
        self._populate_corrections_list()
        self._setup_global_range_controls()
        self._connect_signals()

        QApplication.instance().aboutToQuit.connect(self._cleanup_threads)

    # ------------------------------------------------------------------ #
    # UI wiring
    # ------------------------------------------------------------------ #
    def _connect_signals(self) -> None:
        self.ui.folder_pushButton.clicked.connect(self._on_select_folder)
        self.ui.corrections_listWidget.itemChanged.connect(
            self._on_correction_item_changed
        )

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
    # Corrections list widget
    # ------------------------------------------------------------------ #
    def _populate_corrections_list(self) -> None:
        """Fill QListWidget with available corrections (all *checked*)."""
        lw = self.ui.corrections_listWidget
        lw.blockSignals(True)
        lw.clear()
        for name in self._corr_manager.available_corrections():
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
            item.setCheckState(Qt.Checked)
            lw.addItem(item)
        lw.blockSignals(False)

    # ------------------------------------------------------------------ #
    # Global range controls
    # ------------------------------------------------------------------ #
    def _setup_global_range_controls(self) -> None:
        """Attach validators and signals to the range QLineEdits."""
        validator = QDoubleValidator(bottom=0.0, top=1e9, decimals=6, parent=self)
        validator.setNotation(QDoubleValidator.StandardNotation)

        for le in (self.ui.globalXMin_lineEdit, self.ui.globalXMax_lineEdit):
            le.setValidator(validator)
            le.editingFinished.connect(self._on_global_range_changed)

    def _value_from_line_edit(self, le) -> Optional[float]:
        """Return float value or *None* if empty; pop up on invalid input."""
        text = le.text().strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            self._show_warning(
                "Invalid number",
                f"'{text}' is not a valid numeric value.\n"
                "Please enter an integer or decimal number.",
            )
            le.clear()
            return None

    def _show_warning(self, title: str, message: str) -> None:
        QMessageBox.warning(self.window, title, message)

    @Slot()
    def _on_global_range_changed(self) -> None:
        """Validate & store new global range, then refresh current plot."""
        xmin = self._value_from_line_edit(self.ui.globalXMin_lineEdit)
        xmax = self._value_from_line_edit(self.ui.globalXMax_lineEdit)

        # Consistency check
        if xmin is not None and xmax is not None and xmin >= xmax:
            self._show_warning(
                "Invalid range",
                "The minimum wavelength must be smaller than the maximum.",
            )
            return

        self._global_xmin = xmin
        self._global_xmax = xmax

        # Re-plot current spectrum (if any)
        if self._last_plot_path and self._last_plot_path.exists():
            self._plot_file(self._last_plot_path)

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
        """Refresh table & plot newest spectrum whenever contents change."""
        sorted_files = self._populate_table(files)
        if sorted_files:
            self._plot_file(sorted_files[0])

    # ------------------------------------------------------------------ #
    # Corrections toggled
    # ------------------------------------------------------------------ #
    @Slot(QListWidgetItem)
    def _on_correction_item_changed(self, item: QListWidgetItem) -> None:
        enabled = item.checkState() == Qt.Checked
        self._corr_manager.set_enabled(item.text(), enabled)

        # Re-plot current spectrum
        if self._last_plot_path and self._last_plot_path.exists():
            self._plot_file(self._last_plot_path)

    # ------------------------------------------------------------------ #
    # Table helpers
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
        """Read, correct, fit and plot a single SIF file."""
        try:
            wavelengths_nm, counts = self._read_sif(path)
        except Exception as err:
            print(f"[ERROR] Failed to read {path}: {err}")
            return
        if wavelengths_nm.size == 0 or counts.size == 0:
            return

        # Apply enabled corrections
        corrected_counts = self._corr_manager.apply(wavelengths_nm, counts)

        # ----------------------------------------------------------------
        # Build fit mask from global range line-edits
        # ----------------------------------------------------------------
        fit_mask = np.ones_like(wavelengths_nm, dtype=bool)
        if self._global_xmin is not None:
            fit_mask &= wavelengths_nm >= self._global_xmin
        if self._global_xmax is not None:
            fit_mask &= wavelengths_nm <= self._global_xmax

        # ----------------------------------------------------------------
        # Planck fit on *masked* data
        # ----------------------------------------------------------------
        fit_result = None
        if np.any(fit_mask):  # only fit if at least one point in range
            try:
                fit_result = self._temp_manager.fit(
                    wavelengths_nm[fit_mask], corrected_counts[fit_mask]
                )
                # needed by PlotController
                fit_result["fit_wavelengths"] = wavelengths_nm[fit_mask]
            except Exception as err:
                print(f"[WARNING] Fit failed: {err}")

        # Build title
        title = (
            f"{path.name} — corrected spectrum"
            if any(
                self._corr_manager.is_enabled(n)
                for n in self._corr_manager.available_corrections()
            )
            else f"{path.name} — raw spectrum (no corrections)"
        )

        # Plot
        self._plot_manager.plot_spectrum(
            wavelengths_nm,
            corrected_counts,
            title=title,
            fit=fit_result,
            fit_mask=fit_mask,
        )
        self._last_plot_path = path

    # ---- SIF reader --------------------------------------------------- #
    @staticmethod
    def _read_sif(path: Path) -> Tuple[np.ndarray, np.ndarray]:
        """Return ``wavelengths_nm, counts`` from a SIF file."""
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
