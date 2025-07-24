import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt


class FiberAttenuationCorrector:
    """
    Loads fiber attenuation data from a CSV and applies it to correct
    raw spectrometer counts for fiber optic attenuation.

    CSV format:
        - First row may be a header.
        - Column 1: wavelength in nm
        - Column 2: attenuation in dB/km
        - Column 3: attenuation in dB/m
    """
    def __init__(self, attenuation_csv_path: str, fiber_length_m: float):
        # Load CSV and rename columns
        df = pd.read_csv(attenuation_csv_path)
        df = df.rename(
            columns={
                df.columns[0]: "wavelength_nm",
                df.columns[1]: "attenuation_dbkm",
                df.columns[2]: "attenuation_dbm"
            }
        )
        # Parse numeric columns
        df["wavelength_nm"] = pd.to_numeric(df["wavelength_nm"], errors='coerce')
        df["attenuation_dbm"] = pd.to_numeric(df["attenuation_dbm"], errors='coerce')
        if df[["wavelength_nm", "attenuation_dbm"]].isnull().any().any():
            raise ValueError("Some attenuation values could not be parsed as numbers.")

        # Store data and build interpolator for dB/m
        self._wl = df["wavelength_nm"].values.astype(float)
        self._att_dbm = df["attenuation_dbm"].values.astype(float)
        self._length = float(fiber_length_m)
        self._interp_att = interp1d(
            self._wl,
            self._att_dbm,
            kind="linear",
            bounds_error=False,
            fill_value="extrapolate"
        )

    def _percent_transmission(self, length_m: float | None = None) -> np.ndarray:
        """Return transmission (%) for the stored attenuation curve over a given length."""
        L = self._length if length_m is None else float(length_m)
        total_loss_db = self._att_dbm * L  # dB
        transmission = 10 ** (-total_loss_db / 10.0)  # fraction
        return transmission * 100.0  # percent

    def plot_curve(self, xlim: tuple[float, float] | None = None,
                   length_m: float | None = None,
                   ax=None, **plot_kwargs):
        """
        Plot percent transmission vs wavelength for the fiber.

        Parameters
        ----------
        xlim : (xmin, xmax), optional
            Limits for the wavelength axis in nm.
        length_m : float, optional
            Override the instance fiber length when plotting.
        ax : matplotlib.axes.Axes, optional
            Existing axis to draw on.
        **plot_kwargs :
            Forwarded to matplotlib's `plot`.

        Returns
        -------
        ax : matplotlib.axes.Axes
        """
        if ax is None:
            fig, ax = plt.subplots()

        y_pct = self._percent_transmission(length_m)
        ax.plot(self._wl, y_pct, **plot_kwargs)
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Transmission (%)")
        ax.set_title("Fiber Transmission vs Wavelength")
        if xlim is not None:
            ax.set_xlim(*xlim)
        ax.grid(True, which="both", alpha=0.3)
        return ax

    def correct(self, wavelengths: np.ndarray, counts: np.ndarray) -> np.ndarray:
        """
        Corrects counts for fiber attenuation over the specified cable length.

        Parameters
        ----------
        wavelengths : array-like
            Wavelengths [nm] corresponding to the counts.
        counts : array-like
            Measured counts at each wavelength.

        Returns
        -------
        corrected_counts : np.ndarray
            Counts divided by the fiber transmission fraction.
        """
        # Interpolate dB/m attenuation at measurement wavelengths
        att_dbm_at_meas = self._interp_att(wavelengths)
        # Total loss in dB = dB/m * length (m)
        total_loss_db = att_dbm_at_meas * self._length
        # Transmission fraction = 10^(-loss_dB/10)
        transmission = 10 ** (-total_loss_db / 10)
        if np.any(transmission == 0):
            raise ValueError(
                "Fiber transmission is zero at some wavelengths; cannot correct."
            )
        return counts / transmission
