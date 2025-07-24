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

        # ----------------------- Data curves --------------------------- #
        self._data_curve_in = self._plot_item.plot(
            pen=pg.mkPen("w", width=2), name="Collected spectrum"
        )
        grey_pen = pg.mkPen((150, 150, 150), width=2)
        self._data_curve_out_left = self._plot_item.plot(pen=grey_pen)
        self._data_curve_out_right = self._plot_item.plot(pen=grey_pen)

        # ------------------------ Fit curves --------------------------- #
        red_pen = pg.mkPen("r", width=1.5)
        dark_red_pen = pg.mkPen((140, 20, 20), width=1.5)
        self._fit_curve_in = self._plot_item.plot(pen=red_pen)
        self._fit_curve_out_left = self._plot_item.plot(pen=dark_red_pen)
        self._fit_curve_out_right = self._plot_item.plot(pen=dark_red_pen)

        # Legend (offset ≈ top-left)
        self._legend: pg.LegendItem = self._plot_item.addLegend(
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
        """Plot the spectrum with visual split between in-/out-of-fit ranges."""
        x_full = np.asarray(wavelengths_nm, dtype=float)
        y_full = np.asarray(counts, dtype=float)

        if x_full.size == 0 or y_full.size == 0:
            return  # nothing to display

        # ------------------------------------------------------------------
        # Build/validate mask (default: all True → entire range is "in")
        # ------------------------------------------------------------------
        if fit_mask is None or fit_mask.size != x_full.size:
            fit_mask = np.ones_like(x_full, dtype=bool)

        if not np.any(fit_mask):
            # Degenerate case: nothing selected for fit → treat everything as out
            left_mask = np.ones_like(fit_mask)
            right_mask = np.zeros_like(fit_mask)
        else:
            first_in = np.where(fit_mask)[0][0]
            last_in = np.where(fit_mask)[0][-1]
            left_mask = np.zeros_like(fit_mask, dtype=bool)
            right_mask = np.zeros_like(fit_mask, dtype=bool)
            left_mask[:first_in] = ~fit_mask[:first_in]
            right_mask[last_in + 1 :] = ~fit_mask[last_in + 1 :]

        # -------------------- Data curves (white / grey) ------------------- #
        self._data_curve_in.setData(x_full[fit_mask], y_full[fit_mask])

        if np.any(left_mask):
            self._data_curve_out_left.setData(x_full[left_mask], y_full[left_mask])
        else:
            self._data_curve_out_left.clear()
        if np.any(right_mask):
            self._data_curve_out_right.setData(x_full[right_mask], y_full[right_mask])
        else:
            self._data_curve_out_right.clear()

        # ---------------------- Fit curves (red) --------------------------- #
        if fit and np.any(fit_mask):
            try:
                T = float(fit["T"])
                model_subset = np.asarray(fit["model_counts"], dtype=float)
                lambda_subset = np.asarray(fit.get("fit_wavelengths", x_full[fit_mask]), dtype=float)

                # Estimate overall scale factor so that we can draw the model
                # on the *full* wavelength grid.
                planck_subset = _planck_nm(lambda_subset, T)
                # Least‑squares scaling (protect against zeros)
                denom = np.sum(planck_subset ** 2)
                S = np.sum(model_subset * planck_subset) / denom if denom else 0.0

                model_full = S * _planck_nm(x_full, T)

                # Plot segmented fit curves
                self._fit_curve_in.setData(x_full[fit_mask], model_full[fit_mask])
                if np.any(left_mask):
                    self._fit_curve_out_left.setData(x_full[left_mask], model_full[left_mask])
                else:
                    self._fit_curve_out_left.clear()
                if np.any(right_mask):
                    self._fit_curve_out_right.setData(x_full[right_mask], model_full[right_mask])
                else:
                    self._fit_curve_out_right.clear()
            except Exception:
                # On any error, clear all fit curves (graceful fallback)
                self._fit_curve_in.clear()
                self._fit_curve_out_left.clear()
                self._fit_curve_out_right.clear()
        else:
            # No fit provided → clear curves
            self._fit_curve_in.clear()
            self._fit_curve_out_left.clear()
            self._fit_curve_out_right.clear()

        # -------------------------- Legend -------------------------------- #
        self._legend.clear()
        self._legend.addItem(self._data_curve_in, name="Collected spectrum")
        if fit and np.any(fit_mask):
            T = float(fit["T"])
            T_err = float(fit["T_err"])
            gof = float(fit["gof"])
            gof_label = str(fit.get("gof_label", "R²"))
            legend_label = f"T = {T:.0f} ± {T_err:.0f} K | {gof_label} = {gof:.3f}"
            self._legend.addItem(self._fit_curve_in, legend_label)

        # Auto‑range once, then lock
        self._view_box.autoRange()
        self._plot_item.disableAutoRange()
        self._plot_item.setTitle(title or "")

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _on_mouse_click(self, ev: pg.MouseClickEvent) -> None:
        """Double‑left‑click → auto‑range + lock."""
        if not (ev.double() and ev.button() == Qt.MouseButton.LeftButton):
            return
        if not self._view_box.sceneBoundingRect().contains(ev.scenePos()):
            return  # click outside this ViewBox
        self._view_box.autoRange()
        self._plot_item.disableAutoRange()
