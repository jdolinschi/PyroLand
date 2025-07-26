# file: src/pyroland/controllers/temperature_controller.py
"""
temperature_controller.py
-------------------------

Stateless façade around :class:`src.pyroland.scripts.temperature_fitter.TemperatureFitter`.

* Receives a wavelength grid (nm) and *corrected* counts.
* Returns the best-fit Planck curve evaluated on that grid **plus**
  temperature, 1 σ uncertainty and goodness-of-fit information.

Only this controller knows about the underlying fitting details – the rest of
the application just calls :meth:`fit`.
"""
from __future__ import annotations

from typing import Dict

import numpy as np

from pyroland.scripts.temperature_fitter import TemperatureFitter


__all__ = ["TemperatureController"]


class TemperatureController:
    """Lightweight wrapper around :class:`TemperatureFitter`."""

    def __init__(self, p0: tuple[float, float] | None = None) -> None:
        self._fitter = TemperatureFitter(p0=p0 or (2000, 1e-11))

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def fit(
        self,
        wavelengths_nm: np.ndarray,
        counts: np.ndarray,
        yerr: np.ndarray | None = None,
    ) -> Dict[str, np.ndarray | float | str]:
        """
        Fit a Planck curve to ``counts`` and return both the model and key
        statistics.

        Returns
        -------
        dict
            ``model_counts`` – ndarray, y-values of the fitted curve
            ``T``            – float, temperature [K]
            ``T_err``        – float, 1 σ error on *T*
            ``gof``          – float, goodness-of-fit value
            ``gof_label``    – str, TeX-ready label for the GOF metric
        """
        # Non-linear least squares fit
        T, T_err, S, S_err, gof = self._fitter.fit(
            wavelengths_nm, counts, yerr  # type: ignore[arg-type]
        )

        # Evaluate the model on the *same* wavelength grid
        model_counts = self._fitter._planck(wavelengths_nm * 1e-9, T, S)

        return {
            "model_counts": model_counts,
            "T": T,
            "T_err": T_err,
            "S": S,
            "S_err": S_err,
            "gof": gof,
            "gof_label": self._fitter.gof_label or "",
        }
