# file: src/pyroland/correctors/plot_controller.py
"""
plot_controller.py

A thin layer around a pyqtgraph PlotWidget that knows how to display
a single spectrum (wavelength vs counts).

Double-click reset
------------------
With pyqtgraph ≤ 0.13 there is no ``ViewBox.sigDoubleClick``.  Instead we
listen to the GraphicsScene signal ``sigMouseClicked`` and handle
left-button double-clicks that fall inside this plot’s ViewBox:

    • User double-clicks inside the plot →
      view auto-ranges to fit the data once, then axes are locked again.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QPointF


class PlotController:
    """
    Encapsulates all interactions with a :class:`pyqtgraph.PlotWidget`.

    The public surface is intentionally small – at present we only need to
    replace the plot with a new spectrum on demand.
    """

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    def __init__(self, plot_widget: pg.PlotWidget) -> None:
        self._widget = plot_widget
        self._plot_item: pg.PlotItem = plot_widget.getPlotItem()
        self._view_box: pg.ViewBox = self._plot_item.getViewBox()

        # Cosmetic setup
        self._plot_item.showGrid(x=True, y=True, alpha=0.3)
        self._plot_item.setLabel("bottom", "wavelength (nm)")
        self._plot_item.setLabel("left", "counts (bg corrected)")

        # Single reusable curve
        self._curve = self._plot_item.plot(pen=pg.mkPen(width=2))

        # ------------------------------------------------------------------
        # Hook: double left-click ⇒ reset view to data range
        # ------------------------------------------------------------------
        self._widget.scene().sigMouseClicked.connect(self._on_mouse_click)

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
        Replace the current curve with the supplied data and auto-scale once.

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

        # Fit the view to the data *once* and then lock the axes.
        self._view_box.autoRange()
        self._plot_item.disableAutoRange()

        # Optional title
        self._plot_item.setTitle(title or "")

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _on_mouse_click(self, ev: pg.MouseClickEvent) -> None:
        """
        Handle left-button double-clicks inside this plot’s ViewBox.

        Parameters
        ----------
        ev
            The pyqtgraph MouseClickEvent emitted by the GraphicsScene.
        """
        if not (ev.double() and ev.button() == Qt.MouseButton.LeftButton):
            return  # not the interaction we're after

        # Was the click inside *this* ViewBox?
        scene_pos: QPointF = ev.scenePos()
        if not self._view_box.sceneBoundingRect().contains(scene_pos):
            return  # click happened elsewhere in the window

        # One-shot auto-range then freeze axes
        self._view_box.autoRange()
        self._plot_item.disableAutoRange()
