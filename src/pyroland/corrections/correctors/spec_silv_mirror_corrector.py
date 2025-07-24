# file: silvered_mirror_correction.py
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt


class SilveredMirrorCorrection:
    """
    Correct spectrometer counts for the wavelength-dependent reflectivity of one
    or more internal mirrors.

    CSV format (header row expected):
        ┌───────────────────┬──────────────────────┐
        │ wavelength_nm     │ reflectivity_percent │
        └───────────────────┴──────────────────────┘

    * `wavelength_nm` – Wavelength in nanometres (float).
    * `reflectivity_percent` – Mirror reflectivity in percent (0‒100).

    The reflectivity values are converted to fractions (0‒1).  If *N* mirrors
    are traversed, the total throughput is **R(λ)ⁿ**.  Measured counts are
    therefore divided by that factor:

        counts_true(λ) = counts_measured(λ) / R(λ)ⁿ
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def __init__(self, reflectivity_csv_path: str, n_mirrors: int = 1):
        """
        Parameters
        ----------
        reflectivity_csv_path : str
            Path to the CSV file containing the reflectivity curve.
        n_mirrors : int, optional
            Number of silvered mirrors in the light path (≥ 1).  Default is 1.
        """
        # Validate mirror count
        if not isinstance(n_mirrors, int) or n_mirrors < 1:
            raise ValueError("n_mirrors must be a positive integer (≥ 1).")
        self._n_mirrors = n_mirrors

        # --------------------------------------------------------------
        # 1. Load the CSV and normalise column names
        # --------------------------------------------------------------
        df = pd.read_csv(reflectivity_csv_path)
        df = df.rename(columns={
            df.columns[0]: "wavelength_nm",
            df.columns[1]: "refl_pct"
        })

        # --------------------------------------------------------------
        # 2. Coerce to numeric, stripping stray characters if necessary
        # --------------------------------------------------------------
        df["wavelength_nm"] = pd.to_numeric(df["wavelength_nm"], errors="coerce")
        df["refl_pct"] = pd.to_numeric(
            df["refl_pct"].astype(str).str.replace(r"[^0-9.\-]", "", regex=True),
            errors="coerce"
        )

        if df[["wavelength_nm", "refl_pct"]].isnull().any().any():
            raise ValueError(
                "Some wavelength or reflectivity values could not be parsed as numbers."
            )

        # --------------------------------------------------------------
        # 3. Store arrays and build an interpolator over reflectivity fraction
        # --------------------------------------------------------------
        self._wl = df["wavelength_nm"].values.astype(float)
        self._refl_frac = df["refl_pct"].values / 100.0  # % → fraction

        self._interp_refl = interp1d(
            self._wl,
            self._refl_frac,
            kind="linear",
            bounds_error=False,
            fill_value="extrapolate"
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _percent_reflectivity(self) -> np.ndarray:
        """Return the reflectivity curve in percent (cached)."""
        return self._refl_frac * 100.0

    # ------------------------------------------------------------------
    # Visualisation
    # ------------------------------------------------------------------
    def plot_curve(self, xlim: tuple[float, float] | None = None,
                   ax=None, **plot_kwargs):
        """
        Plot mirror reflectivity (%) vs wavelength.

        Parameters
        ----------
        xlim : (xmin, xmax), optional
            x-axis limits in nanometres.
        ax : matplotlib.axes.Axes, optional
            Existing axis to draw on.
        **plot_kwargs :
            Passed directly to `matplotlib.pyplot.plot`.

        Returns
        -------
        ax : matplotlib.axes.Axes
        """
        if ax is None:
            fig, ax = plt.subplots()

        y_pct = self._percent_reflectivity()
        ax.plot(self._wl, y_pct, **plot_kwargs)
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Reflectivity (%)")
        ax.set_title(f"Mirror Reflectivity vs Wavelength (N = {self._n_mirrors})")
        if xlim is not None:
            ax.set_xlim(*xlim)
        ax.grid(True, which="both", alpha=0.3)
        return ax

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def correct(self, wavelengths: np.ndarray, counts: np.ndarray) -> np.ndarray:
        """
        Apply the mirror-reflectivity correction.

        Parameters
        ----------
        wavelengths : array-like
            Wavelengths [nm] corresponding to *counts*.
        counts : array-like
            Measured counts at each wavelength.

        Returns
        -------
        corrected_counts : np.ndarray
            Counts divided by the cumulative reflectivity R(λ)ⁿ.
        """
        # Interpolate single-bounce reflectivity at measurement wavelengths
        refl_single = self._interp_refl(wavelengths)

        # Total throughput after N reflections
        refl_total = refl_single ** self._n_mirrors

        # Guard against invalid values
        if np.any(refl_total <= 0):
            raise ValueError(
                "Reflectivity is zero or negative at some wavelengths; cannot correct."
            )

        return counts / refl_total
