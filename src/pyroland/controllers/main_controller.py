"""
main_controller.py
==================

High-level GUI controller: orchestrates UI actions, plotting and – now –
file saving / auto-saving of spectrum fits.

*Auto-save Fits* behaviour
--------------------------
When the *Auto-save fits* checkbox is **checked**, **every** spectrum that is
shown in the plot (regardless of when it was added to the folder) is
immediately written to the selected ``.asc`` folder.

Author: Your Name <you@example.com>
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QLineEdit,
    QTableWidgetItem,
)

from sif_parser.utils import parse as sif_parse

from src.pyroland.controllers.plot_controller import PlotController
from src.pyroland.controllers.corrections_controller import CorrectionsController
from src.pyroland.controllers.temperature_controller import TemperatureController
from src.pyroland.controllers.file_controller import FileController

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
        poll_interval: float = 1.0,
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

    # ------------------------------------------------------------------ #
    # Construction / init
    # ------------------------------------------------------------------ #
    def __init__(self, window) -> None:
        super().__init__(window)
        self.window = window
        self.ui = window.ui

        # Helper managers
        self._plot_manager = PlotController(self.ui.plot_widget)
        self._corr_manager = CorrectionsController(fiber_length_m=self._FIBER_LENGTH_M)
        self._temp_manager = TemperatureController()

        # Runtime state -------------------------------------------------- #
        self._current_dir: Optional[Path] = None
        self._watcher: Optional[DirectoryWatcher] = None
        self._last_plot_path: Optional[Path] = None

        # Cached data for saving
        self._last_wavelengths: Optional[np.ndarray] = None
        self._last_counts: Optional[np.ndarray] = None
        self._last_sif_info: Optional[object] = None
        self._last_fit_result: Optional[dict] = None

        # Fitting / plotting limits
        self._global_xmin: Optional[float] = None
        self._global_xmax: Optional[float] = None

        # Auto-save configuration
        self._auto_save_dir: Optional[Path] = None

        # GUI setup ------------------------------------------------------ #
        self._configure_table()
        self._populate_corrections_list()
        self._setup_global_range_controls()
        self._setup_excluded_regions_table()
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
        self.ui.addRegion_pushButton.clicked.connect(self._on_add_region_row)
        self.ui.saveFit_pushButton.clicked.connect(self._on_save_fit_clicked)
        self.ui.autoSaveFits_checkBox.toggled.connect(self._on_auto_save_toggled)

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
        validator = QDoubleValidator(bottom=0.0, top=1e9, decimals=6, parent=self)
        validator.setNotation(QDoubleValidator.StandardNotation)

        for le in (self.ui.globalXMin_lineEdit, self.ui.globalXMax_lineEdit):
            le.setValidator(validator)
            le.editingFinished.connect(self._on_global_range_changed)

    def _value_from_line_edit(self, le) -> Optional[float]:
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
        xmin = self._value_from_line_edit(self.ui.globalXMin_lineEdit)
        xmax = self._value_from_line_edit(self.ui.globalXMax_lineEdit)
        if xmin is not None and xmax is not None and xmin >= xmax:
            self._show_warning(
                "Invalid range",
                "The minimum wavelength must be smaller than the maximum.",
            )
            return
        self._global_xmin = xmin
        self._global_xmax = xmax
        self._replot_if_possible()

    # ------------------------------------------------------------------ #
    # Excluded regions table
    # ------------------------------------------------------------------ #
    def _setup_excluded_regions_table(self) -> None:
        tbl = self.ui.excludedRegions_tableWidget
        tbl.setRowCount(0)
        tbl.setColumnCount(3)  # Remove | x-min | x-max
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(tbl.EditTrigger.NoEditTriggers)
        tbl.setSelectionBehavior(tbl.SelectionBehavior.SelectRows)

    def _on_add_region_row(self) -> None:
        tbl = self.ui.excludedRegions_tableWidget
        row = tbl.rowCount()
        tbl.insertRow(row)

        btn = QPushButton("X", self.window)
        btn.setFixedWidth(24)
        btn.setFixedHeight(24)
        btn.setToolTip("Remove this exclusion region")
        btn.clicked.connect(self._on_remove_region_clicked)
        tbl.setCellWidget(row, 0, btn)

        validator = QDoubleValidator(bottom=0.0, top=1e9, decimals=6, parent=self)
        validator.setNotation(QDoubleValidator.StandardNotation)

        for col, placeholder in enumerate(("x-min", "x-max"), start=1):
            le = QLineEdit()
            le.setPlaceholderText(placeholder)
            le.setValidator(validator)
            le.editingFinished.connect(self._on_region_value_changed)
            tbl.setCellWidget(row, col, le)

    def _on_remove_region_clicked(self) -> None:
        sender = self.sender()
        if not isinstance(sender, QPushButton):
            return
        tbl = self.ui.excludedRegions_tableWidget
        for r in range(tbl.rowCount()):
            if tbl.cellWidget(r, 0) is sender:
                tbl.removeRow(r)
                break
        self._replot_if_possible()

    def _on_region_value_changed(self) -> None:
        tbl = self.ui.excludedRegions_tableWidget
        for r in range(tbl.rowCount()):
            xmin, xmax = self._get_region_row_values(r)
            if xmin is None or xmax is None:
                continue
            if xmin >= xmax:
                self._show_warning(
                    "Invalid region",
                    f"Row {r+1}: x-min must be smaller than x-max.",
                )
                tbl.cellWidget(r, 1).clear()
                tbl.cellWidget(r, 2).clear()
        self._replot_if_possible()

    def _collect_excluded_regions(self) -> List[Tuple[float, float]]:
        regions: List[Tuple[float, float]] = []
        tbl = self.ui.excludedRegions_tableWidget
        for r in range(tbl.rowCount()):
            xmin, xmax = self._get_region_row_values(r)
            if xmin is not None and xmax is not None and xmin < xmax:
                regions.append((xmin, xmax))
        return regions

    def _get_region_row_values(self, row: int) -> Tuple[Optional[float], Optional[float]]:
        tbl = self.ui.excludedRegions_tableWidget
        xmin = self._safe_float_from_line_edit(tbl.cellWidget(row, 1))
        xmax = self._safe_float_from_line_edit(tbl.cellWidget(row, 2))
        return xmin, xmax

    @staticmethod
    def _safe_float_from_line_edit(widget: QLineEdit | None) -> Optional[float]:
        if widget is None:
            return None
        text = widget.text().strip()
        return float(text) if text else None

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
        sorted_files = self._populate_table(files)
        if sorted_files:
            self._plot_file(sorted_files[0])

    # ------------------------------------------------------------------ #
    # Corrections toggled
    # ------------------------------------------------------------------ #
    @Slot(QListWidgetItem)
    def _on_correction_item_changed(self, item: QListWidgetItem) -> None:
        self._corr_manager.set_enabled(item.text(), item.checkState() == Qt.Checked)
        self._replot_if_possible()

    # ------------------------------------------------------------------ #
    # Saving / auto-saving
    # ------------------------------------------------------------------ #
    @Slot()
    def _on_save_fit_clicked(self) -> None:
        if self._last_plot_path is None:
            self._show_warning("No data", "No spectrum is currently plotted.")
            return

        default_name = self._last_plot_path.with_suffix(".asc").name
        start_dir = str(self._current_dir) if self._current_dir else os.getcwd()
        save_path_str, _ = QFileDialog.getSaveFileName(
            parent=self.window,
            caption="Save fit data",
            dir=str(Path(start_dir) / default_name),
            filter="ASC files (*.asc)",
        )
        if save_path_str:
            self._save_fit(Path(save_path_str))

    @Slot(bool)
    def _on_auto_save_toggled(self, checked: bool) -> None:
        if checked:
            start = str(self._current_dir) if self._current_dir else os.getcwd()
            folder = QFileDialog.getExistingDirectory(
                parent=self.window,
                caption="Select folder for auto-saved fits",
                dir=start,
                options=QFileDialog.Option.ShowDirsOnly,
            )
            if not folder:
                self.ui.autoSaveFits_checkBox.setChecked(False)
                return
            self._auto_save_dir = Path(folder)

            # Immediately save currently plotted spectrum, if any
            if self._last_plot_path:
                self._auto_save_current_plot()
        else:
            self._auto_save_dir = None

    def _save_fit(self, save_path: Path) -> None:
        if (
            self._last_wavelengths is None
            or self._last_counts is None
            or self._last_sif_info is None
        ):
            self._show_warning("Nothing to save", "There is no spectrum data in memory.")
            return

        corrections_state: Dict[str, bool] = {
            name: self._corr_manager.is_enabled(name)
            for name in self._corr_manager.available_corrections()
        }

        FileController.save(
            save_path=save_path,
            wavelengths_nm=self._last_wavelengths,
            counts=self._last_counts,
            fit_result=self._last_fit_result,
            sif_info=self._last_sif_info,
            global_xmin=self._global_xmin,
            global_xmax=self._global_xmax,
            excluded_regions=self._collect_excluded_regions(),
            corrections_state=corrections_state,
        )

    def _auto_save_current_plot(self) -> None:
        if self._auto_save_dir and self._last_plot_path:
            asc_path = self._auto_save_dir / f"{self._last_plot_path.stem}.asc"
            self._save_fit(asc_path)

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
        self._plot_file(Path(item.data(Qt.ItemDataRole.UserRole)))

    def _replot_if_possible(self) -> None:
        if self._last_plot_path and self._last_plot_path.exists():
            self._plot_file(self._last_plot_path)

    def _plot_file(self, path: Path) -> None:
        try:
            wavelengths_nm, counts, sif_info = self._read_sif(path)
        except Exception as err:
            print(f"[ERROR] Failed to read {path}: {err}")
            return
        if wavelengths_nm.size == 0:
            return

        corrected_counts = self._corr_manager.apply(wavelengths_nm, counts)

        # Build fit mask
        fit_mask = np.ones_like(wavelengths_nm, dtype=bool)
        if self._global_xmin is not None:
            fit_mask &= wavelengths_nm >= self._global_xmin
        if self._global_xmax is not None:
            fit_mask &= wavelengths_nm <= self._global_xmax
        for xmin, xmax in self._collect_excluded_regions():
            fit_mask &= ~((wavelengths_nm >= xmin) & (wavelengths_nm <= xmax))

        fit_result: Optional[dict] = None
        if np.any(fit_mask):
            try:
                fit_result = self._temp_manager.fit(
                    wavelengths_nm[fit_mask], corrected_counts[fit_mask]
                )
                fit_result["fit_wavelengths"] = wavelengths_nm[fit_mask]
            except Exception as err:
                print(f"[WARNING] Fit failed: {err}")

        title = (
            f"{path.name} — corrected spectrum"
            if any(
                self._corr_manager.is_enabled(n)
                for n in self._corr_manager.available_corrections()
            )
            else f"{path.name} — raw spectrum (no corrections)"
        )

        self._plot_manager.plot_spectrum(
            wavelengths_nm,
            corrected_counts,
            title=title,
            fit=fit_result,
            fit_mask=fit_mask,
        )

        # Cache data for saving
        self._last_plot_path = path
        self._last_wavelengths = wavelengths_nm
        self._last_counts = counts
        self._last_sif_info = sif_info
        self._last_fit_result = fit_result

        # Auto-save if enabled
        self._auto_save_current_plot()

    # ---- SIF reader --------------------------------------------------- #
    @staticmethod
    def _read_sif(path: Path) -> Tuple[np.ndarray, np.ndarray, object]:
        data, info = sif_parse(str(path))
        if data.ndim != 2 or data.shape[1] < 2:
            raise ValueError("Unexpected SIF data shape")
        return np.asarray(data[:, 0], float), np.asarray(data[:, 1], float), info

    # ------------------------------------------------------------------ #
    # Shutdown
    # ------------------------------------------------------------------ #
    @Slot()
    def _cleanup_threads(self) -> None:
        if self._watcher:
            self._watcher.stop()
            self._watcher = None
