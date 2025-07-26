# file: src/pyroland/controllers/plot_controller.py
"""
plot_controller.py  –  gap-without-bridge, v2
------------------------------------------------
Visual artefact fixed *and* excluded segments are visibly
grey (data) / dark-red (fit) once more.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Any, Optional, List, Tuple

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from pyqtgraph.graphicsItems.LegendItem import ItemSample
from pyqtgraph import functions as fn

from pyroland.scripts.temperature_fitter import TemperatureFitter


# --------------------------------------------------------------------------- #
#                               Helper functions                              #
# --------------------------------------------------------------------------- #
def _build_segments(mask: np.ndarray) -> List[Tuple[int, int]]:
    """Return list of contiguous *(start, stop)* slices where mask is True."""
    if mask.size == 0:
        return []
    idx = np.flatnonzero(mask)
    if idx.size == 0:
        return []
    splits = np.where(np.diff(idx) != 1)[0] + 1
    groups = np.split(idx, splits)
    return [(g[0], g[-1] + 1) for g in groups]


# --------------------------------------------------------------------------- #
#                            Custom legend sample                             #
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
#                                PlotController                               #
# --------------------------------------------------------------------------- #
class PlotController:
    """Encapsulates all interactions with a :class:`pyqtgraph.PlotWidget`."""

    # ------------------------- initialisation ------------------------- #
    def __init__(self, plot_widget: pg.PlotWidget) -> None:
        self._widget = plot_widget
        self._plot_item: pg.PlotItem = plot_widget.getPlotItem()
        self._view_box: pg.ViewBox = self._plot_item.getViewBox()

        # Cosmetics
        self._plot_item.showGrid(x=True, y=True, alpha=0.3)
        self._plot_item.setLabel("bottom", "wavelength (nm)")
        self._plot_item.setLabel("left", "counts (bg corrected)")

        # Pens
        self._pen_data_in = pg.mkPen("w", width=2)
        self._pen_data_out = pg.mkPen((150, 150, 150), width=2)
        self._pen_fit_in = pg.mkPen("r", width=1.5)
        self._pen_fit_out = pg.mkPen((140, 20, 20), width=1.5)

        # Primary (in-fit) curves
        self._data_in = self._plot_item.plot(pen=self._pen_data_in,
                                             name="Collected spectrum")
        self._fit_in = self._plot_item.plot(pen=self._pen_fit_in)

        # Pools for excluded segments (data + fit)
        self._data_out_segments: List[pg.PlotDataItem] = []
        self._fit_out_segments: List[pg.PlotDataItem] = []

        # Full tails of Planck curve outside measured domain
        self._fit_tail_left = self._plot_item.plot(pen=self._pen_fit_out)
        self._fit_tail_right = self._plot_item.plot(pen=self._pen_fit_out)
        for tail in (self._fit_tail_left, self._fit_tail_right):
            if hasattr(tail, "setIgnoreBounds"):
                tail.setIgnoreBounds(True)

        # Legend
        self._legend = self._plot_item.addLegend(
            offset=(10, 10), labelTextSize="20pt", sampleType=BigSample
        )

        # Cache for double-click auto-range
        self._last_x: np.ndarray = np.array([])
        self._last_y: np.ndarray = np.array([])

        # Double-click reset
        self._widget.scene().sigMouseClicked.connect(self._on_mouse_click)

    # ------------------------------------------------------------------ #
    # Public API                                                         #
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
        Plot a new spectrum and (optionally) its Planck fit, painting excluded
        regions grey (data) / dark-red (fit) and *without* the bridging artefact.
        """
        x_data = np.asarray(wavelengths_nm, dtype=float)
        y_data = np.asarray(counts, dtype=float)
        if x_data.size == 0:
            return

        # Cache for manual auto-range
        self._last_x = x_data
        self._last_y = y_data

        if fit_mask is None or fit_mask.size != x_data.size:
            fit_mask = np.ones_like(x_data, dtype=bool)

        excluded_segments = _build_segments(~fit_mask)

        # ---------------------------------------------------------------- #
        # 1) Collected spectrum                                            #
        # ---------------------------------------------------------------- #
        self._data_in.setData(x_data, np.where(fit_mask, y_data, np.nan))

        self._ensure_pool(self._data_out_segments,
                          len(excluded_segments),
                          self._pen_data_out)
        for i, (start, stop) in enumerate(excluded_segments):
            self._data_out_segments[i].setData(x_data[start:stop],
                                               y_data[start:stop])
        for j in range(len(excluded_segments), len(self._data_out_segments)):
            self._data_out_segments[j].clear()

        # ---------------------------------------------------------------- #
        # 2) Planck fit                                                    #
        # ---------------------------------------------------------------- #
        self._fit_in.clear()
        for seg in self._fit_out_segments:
            seg.clear()
        self._fit_tail_left.clear()
        self._fit_tail_right.clear()

        if fit and np.any(fit_mask):
            T = float(fit["T"])
            model_subset = np.asarray(fit["model_counts"], dtype=float)
            lambda_subset = np.asarray(
                fit.get("fit_wavelengths", x_data[fit_mask]), dtype=float
            )

            # Scaling factor S
            S = float(fit.get("S", 0.0))
            if S <= 0.0:
                planck_subset = TemperatureFitter._planck(
                    lambda_subset * 1e-9, T, 1.0
                )
                denom = np.sum(planck_subset**2)
                S = np.sum(model_subset * planck_subset) / denom if denom else 0.0

            model_all = TemperatureFitter._planck(x_data * 1e-9, T, S)

            # In-fit part (red, with NaN gaps)
            self._fit_in.setData(x_data,
                                 np.where(fit_mask, model_all, np.nan))

            # Excluded segments (dark red)
            self._ensure_pool(self._fit_out_segments,
                              len(excluded_segments),
                              self._pen_fit_out)
            for i, (start, stop) in enumerate(excluded_segments):
                self._fit_out_segments[i].setData(
                    x_data[start:stop], model_all[start:stop]
                )
            for j in range(len(excluded_segments), len(self._fit_out_segments)):
                self._fit_out_segments[j].clear()

            # Auto-range on visible measured data + fit
            self._view_box.autoRange()
            self._plot_item.disableAutoRange()

            # Planck tails (ignored in range)
            x_left = (np.arange(10.0, x_data.min(), 10.0)
                      if x_data.min() > 10 else np.array([]))
            x_right = (np.arange(x_data.max() + 10.0, 20001.0, 10.0)
                       if x_data.max() < 20000 else np.array([]))

            if x_left.size:
                self._fit_tail_left.setData(
                    x_left, TemperatureFitter._planck(x_left * 1e-9, T, S)
                )
            if x_right.size:
                self._fit_tail_right.setData(
                    x_right, TemperatureFitter._planck(x_right * 1e-9, T, S)
                )
        else:
            # No fit → auto-range on data only
            self._view_box.autoRange()
            self._plot_item.disableAutoRange()

        # ---------------------------------------------------------------- #
        # Legend                                                           #
        # ---------------------------------------------------------------- #
        self._legend.clear()
        self._legend.addItem(self._data_in, "Collected spectrum")
        if fit and np.any(fit_mask):
            self._legend.addItem(
                self._fit_in,
                f"T = {fit['T']:.0f} ± {fit['T_err']:.0f} K, "
                f"R\u00B2 = {fit['gof']:.3f}",
            )

        self._plot_item.setTitle(title or "")

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #
    def _on_mouse_click(self, ev: pg.MouseClickEvent) -> None:
        """Double-left-click → reset to measured spectrum bounds only."""
        if ev.double() and ev.button() == Qt.LeftButton:
            if self._view_box.sceneBoundingRect().contains(ev.scenePos()):
                if self._last_x.size and self._last_y.size:
                    x0, x1 = float(self._last_x.min()), float(self._last_x.max())
                    y0, y1 = float(self._last_y.min()), float(self._last_y.max())
                    if x0 == x1:
                        x0 -= 0.5
                        x1 += 0.5
                    if y0 == y1:
                        y0 -= 1
                        y1 += 1
                    self._plot_item.setRange(
                        xRange=(x0, x1), yRange=(y0, y1), padding=0.05
                    )
                    self._plot_item.disableAutoRange()
                else:
                    self._view_box.autoRange()
                    self._plot_item.disableAutoRange()

    def _ensure_pool(
        self, pool: List[pg.PlotDataItem], size: int, pen: pg.functions.mkPen
    ) -> None:
        """Make sure *pool* contains at least *size* PlotDataItems."""
        while len(pool) < size:
            pool.append(self._plot_item.plot(pen=pen))
