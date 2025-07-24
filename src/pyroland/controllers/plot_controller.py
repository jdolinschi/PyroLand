# file: src/pyroland/controllers/plot_controller.py
"""
plot_controller.py

Wrapper around a :class:`pyqtgraph.PlotWidget` that knows how to draw:

    • The spectrum points *used* for fitting (white, thick line)
    • Any spectrum points *excluded* from the fit (grey, thick line)
    • The best-fit Planck curve (red, thin line, drawn on top)

A fixed legend in the top-left corner displays the fitted temperature
(± 1 σ) and the goodness-of-fit metric.

Double-click anywhere inside the plot to auto-range and lock the axes.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Any, Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from pyqtgraph.graphicsItems.LegendItem import ItemSample
from pyqtgraph import functions as fn


class BigSample(ItemSample):
    """
    Custom legend sample that draws a thicker, larger horizontal line
    without the default small sample to avoid duplication.
    """

    def __init__(self, item):
        super().__init__(item)
        # enlarge box so the line is clearly visible
        self.setFixedWidth(40)
        self.setFixedHeight(40)

    def paint(self, painter, *args):  # noqa: D401
        # Draw only a thick centred horizontal line
        opts = self.item.opts
        pen = fn.mkPen(opts["pen"])
        pen.setWidth(3)
        painter.setPen(pen)
        h = self.height() / 2
        w = self.width() - 2
        painter.drawLine(1, h, w, h)


class PlotController:
    """
    Encapsulates all interactions with a :class:`pyqtgraph.PlotWidget`.

    The class owns three reusable curves:

        • Data (IN fit range)   – white, 2 px
        • Data (OUT of range)   – grey,  2 px
        • Fit                   – red,   1.5 px
    """

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

        # Curves
        self._data_curve_in = self._plot_item.plot(
            pen=pg.mkPen("w", width=2), name="Collected spectrum"
        )
        self._data_curve_out = self._plot_item.plot(
            pen=pg.mkPen((150, 150, 150), width=2)
        )
        self._fit_curve = self._plot_item.plot(pen=pg.mkPen("r", width=1.5))

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
        """
        Replace the current curves with new data (+ optional fit).

        Parameters
        ----------
        wavelengths_nm
            Iterable of floats [nm] (full range)
        counts
            Iterable of floats [counts] (full range)
        title
            Optional plot title
        fit
            Mapping from :meth:`TemperatureController.fit` or *None*
            Must contain keys ``"model_counts"`` and ``"fit_wavelengths"``
            if provided.
        fit_mask
            Boolean ndarray marking which points were *included* in the fit.
            If *None*, the entire data set is considered in-range.
        """
        x = np.asarray(wavelengths_nm, dtype=float)
        y = np.asarray(counts, dtype=float)

        if x.size == 0 or y.size == 0:
            return  # nothing to display

        # --- Split data into “in” / “out” regions --------------------- #
        if fit_mask is None or fit_mask.size != x.size:
            fit_mask = np.ones_like(x, dtype=bool)

        self._data_curve_in.setData(x[fit_mask], y[fit_mask])
        self._data_curve_out.setData(x[~fit_mask], y[~fit_mask])

        # Fit curve
        if fit:
            fit_x = np.asarray(fit.get("fit_wavelengths", []), dtype=float)
            model_y = np.asarray(fit["model_counts"], dtype=float)
            if fit_x.size and model_y.size and fit_x.size == model_y.size:
                self._fit_curve.setData(fit_x, model_y)
            else:
                self._fit_curve.clear()
        else:
            self._fit_curve.clear()

        # Legend (refresh each call)
        self._legend.clear()
        self._legend.addItem(self._data_curve_in, name="Collected spectrum")
        if fit:
            T = float(fit["T"])
            T_err = float(fit["T_err"])
            gof = float(fit["gof"])
            gof_label = str(fit.get("gof_label", "R²"))
            legend_label = f"T = {T:.0f} \u00B1 {T_err:.0f} K | R\u00B2 = {gof:.3f}"
            self._legend.addItem(self._fit_curve, legend_label)

        # Auto-range once, then lock
        self._view_box.autoRange()
        self._plot_item.disableAutoRange()
        self._plot_item.setTitle(title or "")

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _on_mouse_click(self, ev: pg.MouseClickEvent) -> None:
        """Double-left-click → auto-range + lock."""
        if not (ev.double() and ev.button() == Qt.MouseButton.LeftButton):
            return

        if not self._view_box.sceneBoundingRect().contains(ev.scenePos()):
            return  # click outside this ViewBox

        self._view_box.autoRange()
        self._plot_item.disableAutoRange()
