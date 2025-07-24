# file: src/pyroland/controllers/plot_controller.py
"""
plot_controller.py

Wrapper around a :class:`pyqtgraph.PlotWidget` that knows how to draw

    • Spectrum points *used* for fitting   – white,  2 px
    • Spectrum points *excluded* from fit – grey,   2 px (left & right segments)
    • Best‑fit Planck curve (in‑range)     – bright red, 1.5 px
    • Best‑fit Planck curve (out‑of‑range) – muted  red, 1.5 px (left & right)

A fixed legend in the top‑left corner displays the fitted temperature
(± 1 σ) together with the goodness‑of‑fit metric.

Double‑click anywhere inside the plot to auto‑range and lock the axes.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Any, Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from pyqtgraph.graphicsItems.LegendItem import ItemSample
from pyqtgraph import functions as fn

from src.pyroland.scripts.temperature_fitter import TemperatureFitter

# --------------------------------------------------------------------------- #
#                               Helpers                                       #
# --------------------------------------------------------------------------- #

def _planck_nm(lambda_nm: np.ndarray | float, T: float) -> np.ndarray:
    """Planck spectral radiance *per unit wavelength* (arbitrary units).

    The absolute scaling will later be absorbed into an overall multiplicative
    factor, so physical units are not important here – only the functional
    dependence on *λ* and *T* matters.
    """
    h = 6.626_070_15e-34  # Planck [J s]
    c = 2.997_924_58e8    # speed of light [m s⁻¹]
    k = 1.380_649e-23     # Boltzmann [J K⁻¹]

    lam = np.asarray(lambda_nm, dtype=float) * 1e-9  # nm → m
    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        expo = np.exp(h * c / (lam * k * T)) - 1.0
        rad = (2.0 * h * c ** 2) / (lam ** 5 * expo)
    return rad


class BigSample(ItemSample):
    """Legend sample that shows a thicker horizontal line (no tiny square)."""

    def __init__(self, item):
        super().__init__(item)
        self.setFixedWidth(40)
        self.setFixedHeight(40)

    def paint(self, painter, *args):  # noqa: D401
        opts = self.item.opts
        pen = fn.mkPen(opts["pen"])
        pen.setWidth(3)
        painter.setPen(pen)
        h = self.height() / 2
        w = self.width() - 2
        painter.drawLine(1, h, w, h)


class PlotController:
    """Encapsulates all interactions with a :class:`pyqtgraph.PlotWidget`."""

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    def __init__(self, plot_widget: pg.PlotWidget) -> None:
        self._widget = plot_widget
        self._plot_item: pg.PlotItem = plot_widget.getPlotItem()
        self._view_box: pg.ViewBox = self._plot_item.getViewBox()

        # Cosmetics
        self._plot_item.showGrid(x=True, y=True, alpha=0.3)
        self._plot_item.setLabel("bottom", "wavelength (nm)")
        self._plot_item.setLabel("left", "counts (bg corrected)")

        # ------------ Spectrum curves ------------
        white_pen = pg.mkPen("w", width=2)
        grey_pen = pg.mkPen((150, 150, 150), width=2)
        self._data_in = self._plot_item.plot(pen=white_pen, name="Collected spectrum")
        self._data_out_left = self._plot_item.plot(pen=grey_pen)
        self._data_out_right = self._plot_item.plot(pen=grey_pen)

        # -------------- Fit curves ---------------
        red_pen = pg.mkPen("r", width=1.5)
        dark_red_pen = pg.mkPen((140, 20, 20), width=1.5)
        self._fit_in = self._plot_item.plot(pen=red_pen)
        self._fit_out_left = self._plot_item.plot(pen=dark_red_pen)
        self._fit_out_right = self._plot_item.plot(pen=dark_red_pen)

        # Legend
        self._legend = self._plot_item.addLegend(
            offset=(10, 10), labelTextSize="20pt", sampleType=BigSample
        )

        # Double-click reset
        self._widget.scene().sigMouseClicked.connect(self._on_mouse_click)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def plot_spectrum(
        self,
        wavelengths_nm: Iterable[float],
        counts: Iterable[float],
        *,
        title: str | None = None,
        fit: Optional[Mapping[str, Any]] = None,
        fit_mask: Optional[np.ndarray] = None,
    ) -> None:
        """Refresh plot with a new spectrum + (optional) fit."""
        x_data = np.asarray(wavelengths_nm, dtype=float)
        y_data = np.asarray(counts, dtype=float)
        if x_data.size == 0:
            return

        # ----------- Build boolean masks (fit vs non-fit) -----------
        if fit_mask is None or fit_mask.size != x_data.size:
            fit_mask = np.ones_like(x_data, dtype=bool)

        first_in = np.where(fit_mask)[0][0] if np.any(fit_mask) else 0
        last_in = np.where(fit_mask)[0][-1] if np.any(fit_mask) else x_data.size - 1

        left_mask = np.arange(x_data.size) < first_in
        right_mask = np.arange(x_data.size) > last_in

        # ------------------- Plot data curves -----------------------
        self._data_in.setData(x_data[fit_mask], y_data[fit_mask])
        self._data_out_left.setData(x_data[left_mask], y_data[left_mask]) \
            if np.any(left_mask) else self._data_out_left.clear()
        self._data_out_right.setData(x_data[right_mask], y_data[right_mask]) \
            if np.any(right_mask) else self._data_out_right.clear()

        # --------------- Prepare / draw fit curves ------------------
        # Stage 1 – draw only the *in-fit* part so autoRange ignores the
        # long tails.  Stage 2 (after autoRange) adds the extrapolated tails.
        self._fit_out_left.clear()
        self._fit_out_right.clear()

        if fit and np.any(fit_mask):
            T = float(fit["T"])
            model_subset = np.asarray(fit["model_counts"], dtype=float)
            lambda_subset = np.asarray(fit.get("fit_wavelengths", x_data[fit_mask]),
                                       dtype=float)

            # Preferred: use S from TemperatureController
            S = float(fit.get("S", 0.0))
            if S <= 0.0:
                # Fallback: least-squares scaling against our own Planck impl.
                planck_subset = TemperatureFitter._planck(lambda_subset * 1e-9, T, 1.0)
                denom = np.sum(planck_subset ** 2)
                S = np.sum(model_subset * planck_subset) / denom if denom else 0.0

            # In-data model for immediate display
            model_in_data = TemperatureFitter._planck(x_data * 1e-9, T, S)
            self._fit_in.setData(x_data[fit_mask], model_in_data[fit_mask])

            # ------------------- Auto-range now ----------------------
            self._view_box.autoRange()
            self._plot_item.disableAutoRange()

            # ------------- Build full (1 nm-20 000 nm) curve ----------
            x_left = np.arange(10, x_data.min(), 10.0)  # 10 nm → before data
            x_right = np.arange(x_data.max() + 10.0, 20001.0, 10.0)
            x_full = np.concatenate((x_left, x_data, x_right))
            y_full = TemperatureFitter._planck(x_full * 1e-9, T, S)

            # Masks for the long tails
            left_tail_mask = x_full < x_data[first_in]
            right_tail_mask = x_full > x_data[last_in]

            self._fit_out_left.setData(x_full[left_tail_mask],
                                       y_full[left_tail_mask])
            self._fit_out_right.setData(x_full[right_tail_mask],
                                        y_full[right_tail_mask])
        else:
            self._fit_in.clear()
            self._view_box.autoRange()
            self._plot_item.disableAutoRange()

        # ------------------------ Legend ---------------------------
        self._legend.clear()
        self._legend.addItem(self._data_in, "Collected spectrum")
        if fit and np.any(fit_mask):
            legend_txt = (
                f"T = {fit['T']:.0f} ± {fit['T_err']:.0f} K | "
                f"{fit.get('gof_label', 'R²')} = {fit['gof']:.3f}"
            )
            self._legend.addItem(self._fit_in, legend_txt)

        self._plot_item.setTitle(title or "")

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #
    def _on_mouse_click(self, ev: pg.MouseClickEvent) -> None:
        """Double-left-click → auto-range + lock."""
        if ev.double() and ev.button() == Qt.MouseButton.LeftButton:
            if self._view_box.sceneBoundingRect().contains(ev.scenePos()):
                self._view_box.autoRange()
                self._plot_item.disableAutoRange()
