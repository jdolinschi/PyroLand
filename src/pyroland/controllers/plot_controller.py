# file: src/pyroland/controllers/plot_controller.py
"""
plot_controller.py

Wrapper around a :class:`pyqtgraph.PlotWidget` that knows how to draw:

    • The *corrected* spectrum (white, thick line)
    • The best-fit Planck curve (red, thin line, drawn on top)

A fixed legend in the top-left corner displays the fitted temperature
(± 1 σ) and the goodness-of-fit metric.

Double-click anywhere inside the plot to auto-range and lock the axes.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QPointF


class PlotController:
    """
    Encapsulates all interactions with a :class:`pyqtgraph.PlotWidget`.

    The class owns two reusable curves:
        1. Data (white, 2 px)
        2. Fit  (red, 1.5 px)
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
        self._data_curve = self._plot_item.plot(
            pen=pg.mkPen("w", width=2),
            name="data",
        )
        self._fit_curve = self._plot_item.plot(
            pen=pg.mkPen("r", width=1.5),
        )

        # Legend (offset ≈ top-left)
        self._legend: pg.LegendItem = self._plot_item.addLegend(offset=(10, 10))

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
        fit: Mapping[str, Any] | None = None,
    ) -> None:
        """
        Replace the current curves with new data (+ optional fit).

        Parameters
        ----------
        wavelengths_nm
            Iterable of floats [nm]
        counts
            Iterable of floats [counts]
        title
            Optional plot title
        fit
            Mapping from :meth:`TemperatureController.fit` or *None*
        """
        x = np.asarray(wavelengths_nm, dtype=float)
        y = np.asarray(counts, dtype=float)

        if x.size == 0 or y.size == 0:
            return  # nothing to display

        # Data curve
        self._data_curve.setData(x, y)

        # Fit curve
        if fit:
            model_y = np.asarray(fit["model_counts"], dtype=float)
            self._fit_curve.setData(x, model_y)
        else:
            self._fit_curve.clear()

        # Legend (refresh each call)
        self._legend.clear()
        self._legend.addItem(self._data_curve, name='Collected spectrum')
        if fit:
            T = float(fit["T"])
            T_err = float(fit["T_err"])
            gof = float(fit["gof"])
            gof_label = str(fit.get("gof_label", ""))
            legend_label = f"T = {T:.0f} ± {T_err:.0f} K · {gof_label} = {gof:.3f}"
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
