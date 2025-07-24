# file: lens_correction.py
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt


class QTHLensTransmissionCorrector:
    """
    Compensates raw spectrometer counts for the wavelength-dependent
    transmission of a lens, window, or other optic in the beam path.

    CSV format (header row expected):
        ┌───────────────────┬───────────────────────┐
        │ wavelength_nm     │ percent_transmission  │
        └───────────────────┴───────────────────────┘

    * `wavelength_nm` – Wavelength in nanometres (float).
    * `percent_transmission` – Transmission in percent (0‒100).

    The percentage values are internally converted to fractions (0‒1).
    During correction, measured counts are divided by the transmission
    fraction so that regions of lower transmission are boosted and
    regions of higher transmission are reduced accordingly.
    """

    def __init__(self, transmission_csv_path: str):
        # ------------------------------------------------------------------
        # 1. Load the CSV and normalise column names
        # ------------------------------------------------------------------
        df = pd.read_csv(transmission_csv_path)
        df = df.rename(columns={
            df.columns[0]: "wavelength_nm",
            df.columns[1]: "trans_pct"
        })

        # ------------------------------------------------------------------
        # 2. Coerce to numeric, stripping stray characters if necessary
        # ------------------------------------------------------------------
        df["wavelength_nm"] = pd.to_numeric(df["wavelength_nm"], errors="coerce")
        df["trans_pct"] = pd.to_numeric(
            df["trans_pct"].astype(str).str.replace(r"[^0-9.\-]", "", regex=True),
            errors="coerce"
        )

        if df[["wavelength_nm", "trans_pct"]].isnull().any().any():
            raise ValueError(
                "Some wavelength or transmission values could not be parsed as numbers."
            )

        # ------------------------------------------------------------------
        # 3. Store arrays and build an interpolator over transmission fraction
        # ------------------------------------------------------------------
        self._wl = df["wavelength_nm"].values.astype(float)
        self._trans_frac = df["trans_pct"].values / 100.0  # convert % → fraction

        self._interp_trans = interp1d(
            self._wl,
            self._trans_frac,
            kind="linear",
            bounds_error=False,
            fill_value="extrapolate"
        )

    def _percent_transmission(self) -> np.ndarray:
        return self._trans_frac * 100.0

    def plot_curve(self, xlim: tuple[float, float] | None = None,
                   ax=None, **plot_kwargs):
        """
        Plot lens transmission (%) vs wavelength.
        """
        if ax is None:
            fig, ax = plt.subplots()

        y_pct = self._percent_transmission()
        ax.plot(self._wl, y_pct, **plot_kwargs)
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Transmission (%)")
        ax.set_title("Lens Transmission vs Wavelength")
        if xlim is not None:
            ax.set_xlim(*xlim)
        ax.grid(True, which="both", alpha=0.3)
        return ax

    # ----------------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------------
    def correct(self, wavelengths: np.ndarray, counts: np.ndarray) -> np.ndarray:
        """
        Apply the lens-transmission correction.

        Parameters
        ----------
        wavelengths : array-like
            Wavelengths [nm] corresponding to ``counts``.
        counts : array-like
            Measured counts at each wavelength.

        Returns
        -------
        corrected_counts : np.ndarray
            Counts divided by the lens transmission fraction at each wavelength,
            i.e. ``counts_true = counts_measured / T(λ)``.
        """
        # Interpolate transmission fraction at the measurement wavelengths
        trans_at_meas = self._interp_trans(wavelengths)

        # Guard against division by zero or negative values
        if np.any(trans_at_meas <= 0):
            raise ValueError(
                "Lens transmission is zero or negative at some wavelengths; "
                "cannot correct."
            )

        return counts / trans_at_meas
