# file: src/pyroland/controllers/plot_controller.py
"""
plot_controller.py (refactored again)

- Arbitrary excluded regions via fit_mask (grey/dark red segments).
- Full Planck tails (10–20 000 nm) are shown but NEVER drive autoRange.
- Double-left-click reset now restores the view to the raw spectrum range only.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Any, Optional, List, Tuple

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from pyqtgraph.graphicsItems.LegendItem import ItemSample
from pyqtgraph import functions as fn

from src.pyroland.scripts.temperature_fitter import TemperatureFitter


def _planck_nm(lambda_nm: np.ndarray | float, T: float) -> np.ndarray:
    """Planck spectral radiance *per unit wavelength* (arbitrary units)."""
    h = 6.626_070_15e-34  # Planck [J s]
    c = 2.997_924_58e8    # speed of light [m s⁻¹]
    k = 1.380_649e-23     # Boltzmann [J K⁻¹]

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
    """Encapsulates interactions with a :class:`pyqtgraph.PlotWidget`."""

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

        # Pools for excluded segments (data + fit) within measured domain
        self._data_out_segments: List[pg.PlotDataItem] = []
        self._fit_out_segments: List[pg.PlotDataItem] = []

        # Full tails of Planck curve outside measured domain
        self._fit_tail_left = self._plot_item.plot(pen=self._pen_fit_out)
        self._fit_tail_right = self._plot_item.plot(pen=self._pen_fit_out)

        # (Optional) help pyqtgraph ignore bounds of tails when auto-ranging
        # If your pyqtgraph version supports it:
        for tail in (self._fit_tail_left, self._fit_tail_right):
            if hasattr(tail, "setIgnoreBounds"):
                tail.setIgnoreBounds(True)

        # Legend
        self._legend = self._plot_item.addLegend(
            offset=(10, 10), labelTextSize="20pt", sampleType=BigSample
        )

        # Data cache for custom auto-range on double-click
        self._last_x: np.ndarray = np.array([])
        self._last_y: np.ndarray = np.array([])

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
        Refresh plot with a new spectrum + (optional) fit.
        """
        x_data = np.asarray(wavelengths_nm, dtype=float)
        y_data = np.asarray(counts, dtype=float)
        if x_data.size == 0:
            return

        self._last_x = x_data   # cache for manual auto-range
        self._last_y = y_data

        if fit_mask is None or fit_mask.size != x_data.size:
            fit_mask = np.ones_like(x_data, dtype=bool)

        # Identify segments excluded from fit
        excluded_segments = _build_segments(~fit_mask)

        # ------------------- Plot DATA -------------------
        self._data_in.setData(x_data[fit_mask], y_data[fit_mask])

        self._ensure_pool(self._data_out_segments, len(excluded_segments), self._pen_data_out)
        for i, (start, stop) in enumerate(excluded_segments):
            self._data_out_segments[i].setData(x_data[start:stop], y_data[start:stop])
        for j in range(len(excluded_segments), len(self._data_out_segments)):
            self._data_out_segments[j].clear()

        # ------------------- Plot FIT --------------------
        self._fit_in.clear()
        for seg in self._fit_out_segments:
            seg.clear()
        self._fit_tail_left.clear()
        self._fit_tail_right.clear()

        if fit and np.any(fit_mask):
            T = float(fit["T"])
            model_subset = np.asarray(fit["model_counts"], dtype=float)
            lambda_subset = np.asarray(fit.get("fit_wavelengths", x_data[fit_mask]),
                                       dtype=float)

            # Scaling factor S
            S = float(fit.get("S", 0.0))
            if S <= 0.0:
                planck_subset = TemperatureFitter._planck(lambda_subset * 1e-9, T, 1.0)
                denom = np.sum(planck_subset ** 2)
                S = np.sum(model_subset * planck_subset) / denom if denom else 0.0

            # Model over measured domain
            model_all = TemperatureFitter._planck(x_data * 1e-9, T, S)
            self._fit_in.setData(x_data[fit_mask], model_all[fit_mask])

            # Excluded segments inside measured domain
            self._ensure_pool(self._fit_out_segments, len(excluded_segments), self._pen_fit_out)
            for i, (start, stop) in enumerate(excluded_segments):
                self._fit_out_segments[i].setData(x_data[start:stop], model_all[start:stop])
            for j in range(len(excluded_segments), len(self._fit_out_segments)):
                self._fit_out_segments[j].clear()

            # Auto-range ONLY on measured data + in-fit portion (already plotted)
            self._view_box.autoRange()
            self._plot_item.disableAutoRange()

            # ---- Plot full tails (10–20 000 nm) WITHOUT changing view ----
            x_left = np.arange(10.0, x_data.min(), 10.0) if x_data.min() > 10 else np.array([])
            x_right = np.arange(x_data.max() + 10.0, 20001.0, 10.0) if x_data.max() < 20000 else np.array([])

            if x_left.size:
                y_left = TemperatureFitter._planck(x_left * 1e-9, T, S)
                self._fit_tail_left.setData(x_left, y_left)
            if x_right.size:
                y_right = TemperatureFitter._planck(x_right * 1e-9, T, S)
                self._fit_tail_right.setData(x_right, y_right)

        else:
            # No fit: just auto-range on spectrum
            self._view_box.autoRange()
            self._plot_item.disableAutoRange()

        # ---------------- Legend ----------------
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
        """Double-left-click → reset to measured spectrum bounds only."""
        if ev.double() and ev.button() == Qt.MouseButton.LeftButton:
            if self._view_box.sceneBoundingRect().contains(ev.scenePos()):
                if self._last_x.size and self._last_y.size:
                    x0, x1 = float(self._last_x.min()), float(self._last_x.max())
                    y0, y1 = float(self._last_y.min()), float(self._last_y.max())
                    # Avoid zero-height/width ranges
                    if x0 == x1:
                        x0 -= 0.5
                        x1 += 0.5
                    if y0 == y1:
                        y0 -= 1
                        y1 += 1
                    self._plot_item.setRange(xRange=(x0, x1), yRange=(y0, y1), padding=0.05)
                    self._plot_item.disableAutoRange()
                else:
                    # Fallback if no cache
                    self._view_box.autoRange()
                    self._plot_item.disableAutoRange()

    def _ensure_pool(self, pool: List[pg.PlotDataItem], size: int, pen: pg.functions.mkPen) -> None:
        """Ensure *pool* has at least *size* PlotDataItems with given *pen*."""
        while len(pool) < size:
            item = self._plot_item.plot(pen=pen)
            pool.append(item)


def _build_segments(mask: np.ndarray) -> List[Tuple[int, int]]:
    """Return list of (start, stop) slices where mask==True (contiguous).

    Example:
      mask = [F F T T F T] -> segments = [(2,4), (5,6)]
    """
    if mask.size == 0:
        return []
    idx = np.flatnonzero(mask)
    if idx.size == 0:
        return []
    splits = np.where(np.diff(idx) != 1)[0] + 1
    groups = np.split(idx, splits)
    return [(g[0], g[-1] + 1) for g in groups]
