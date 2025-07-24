# file: src/pyroland/controllers/plot_controller.py
"""
plot_controller.py

A thin layer around a pyqtgraph PlotWidget that knows how to display
a single spectrum (wavelength vs counts).

Keeping all plotting responsibilities in this class makes the UI
controller lighter and allows easy future extension (e.g. zoom tools,
export, multiple traces, annotations, …).
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pyqtgraph as pg


class PlotController:
    """
    Encapsulates all interactions with a :class:`pyqtgraph.PlotWidget`.

    The public surface is intentionally small – at present we only need to
    replace the plot with a new spectrum on demand.
    """

    def __init__(self, plot_widget: pg.PlotWidget) -> None:
        # Keep a reference to the widget and its ViewBox / PlotItem
        self._widget = plot_widget
        self._plot_item = plot_widget.getPlotItem()
        self._plot_item.showGrid(x=True, y=True, alpha=0.3)

        # Fixed axis labels
        self._plot_item.setLabel("bottom", "wavelength (nm)")
        self._plot_item.setLabel("left", "counts (bg corrected)")

        # A single curve object that we reuse for every update
        self._curve = self._plot_item.plot(pen=pg.mkPen(width=2))

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def plot_spectrum(
        self,
        wavelengths_nm: Iterable[float],
        counts: Iterable[float],
        title: str | None = None,
    ) -> None:
        """
        Replace the current curve with the supplied data and auto–scale once.

        Parameters
        ----------
        wavelengths_nm
            1-D iterable of floats (nanometres).
        counts
            1-D iterable of floats (counts).
        title
            Optional title shown above the plot.
        """
        x = np.asarray(wavelengths_nm, dtype=float)
        y = np.asarray(counts, dtype=float)

        if x.size == 0 or y.size == 0:
            return  # nothing to display

        # Update the curve data
        self._curve.setData(x, y)

        # One-shot auto-scale: fit the view *once*, then lock it.
        vb = self._plot_item.getViewBox()
        vb.autoRange()               # compute visible range
        self._plot_item.disableAutoRange()   # freeze both axes

        # Optional title
        self._plot_item.setTitle(title or "")
