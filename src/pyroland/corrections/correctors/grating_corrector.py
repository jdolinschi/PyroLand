import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt


class GratingEfficiencyCorrector:
    """
    Loads a grating efficiency curve from a CSV and applies it to correct
    raw spectrometer counts for the grating efficiency.

    CSV format:
        - First row may be a header.
        - First column: wavelength in nm
        - Second column: grating efficiency in percent (0–100);
    """
    def __init__(self, efficiency_csv_path: str):
        # Load the CSV into a DataFrame, allowing for a header row
        df = pd.read_csv(efficiency_csv_path)
        # Rename first two columns to known names
        df = df.rename(columns={df.columns[0]: "wavelength_nm", df.columns[1]: "eff_pct"})

        # Convert efficiency column to numeric, stripping non-numeric characters
        df["eff_pct"] = pd.to_numeric(
            df["eff_pct"].astype(str)
               .str.replace(r"[^0-9\.\-]", "", regex=True),
            errors='coerce'
        )
        if df["eff_pct"].isnull().any():
            raise ValueError("Some efficiency values could not be parsed as numbers.")

        # Store wavelengths in nm and convert efficiency to fraction
        self._wl = df["wavelength_nm"].values.astype(float)
        self._eff = (df["eff_pct"].values / 100.0)

        # Build a linear interpolator (extrapolate outside the range)
        self._interp = interp1d(
            self._wl,
            self._eff,
            kind="linear",
            bounds_error=False,
            fill_value="extrapolate"
        )

    def _percent_efficiency(self) -> np.ndarray:
        return self._eff * 100.0

    def plot_curve(self, xlim: tuple[float, float] | None = None,
                   ax=None, **plot_kwargs):
        """
        Plot grating efficiency (%) vs wavelength.
        """
        if ax is None:
            fig, ax = plt.subplots()

        y_pct = self._percent_efficiency()
        ax.plot(self._wl, y_pct, **plot_kwargs)
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Efficiency (%)")
        ax.set_title("Grating Efficiency vs Wavelength")
        if xlim is not None:
            ax.set_xlim(*xlim)
        ax.grid(True, which="both", alpha=0.3)
        return ax

    def correct(self, wavelengths: np.ndarray, counts: np.ndarray) -> np.ndarray:
        """
        Corrects counts for grating efficiency.

        Parameters
        ----------
        wavelengths : array-like
            Wavelengths [nm] for the measured counts.
        counts : array-like
            Measured counts at each wavelength.

        Returns
        -------
        corrected_counts : np.ndarray
            Counts divided by the grating efficiency at each wavelength.
        """
        # Interpolate efficiency at each measurement wavelength
        eff_at_measured = self._interp(wavelengths)

        # Prevent division by zero
        if np.any(eff_at_measured == 0):
            raise ValueError(
                "Grating efficiency is zero at some wavelengths; cannot correct."
            )

        return counts / eff_at_measured
