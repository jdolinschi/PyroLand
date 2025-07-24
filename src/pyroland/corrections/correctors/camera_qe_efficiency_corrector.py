import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt

class QuantumEfficiencyCorrector:
    """
    Loads a camera quantum‐efficiency curve from a CSV and applies it to correct
    raw spectrometer counts for the detector’s wavelength‐dependent response.

    CSV format (with header):
        - Column 1: wavelength_nm
        - Column 2: quantum_effiency_percent
    """
    def __init__(self, qe_csv_path: str):
        # 1) Load CSV (header row assumed) and rename columns
        df = pd.read_csv(qe_csv_path)
        df = df.rename(columns={
            df.columns[0]: "wavelength_nm",
            df.columns[1]: "qe_pct"
        })

        # 2) Coerce to numeric, strip non‑digits if necessary
        df["wavelength_nm"] = pd.to_numeric(df["wavelength_nm"], errors="coerce")
        df["qe_pct"]       = pd.to_numeric(
            df["qe_pct"].astype(str).str.replace(r"[^0-9\.\-]", "", regex=True),
            errors="coerce"
        )
        if df[["wavelength_nm","qe_pct"]].isnull().any().any():
            raise ValueError("Some quantum‐efficiency values could not be parsed as numbers.")

        # 3) Store arrays and build an interpolator over QE fraction
        self._wl  = df["wavelength_nm"].values.astype(float)
        self._qe  = (df["qe_pct"].values / 100.0)
        self._interp_qe = interp1d(
            self._wl,
            self._qe,
            kind="linear",
            bounds_error=False,
            fill_value="extrapolate"
        )

    def _percent_qe(self) -> np.ndarray:
        return self._qe * 100.0

    def plot_curve(self, xlim: tuple[float, float] | None = None,
                   ax=None, **plot_kwargs):
        """
        Plot detector quantum efficiency (%) vs wavelength.
        """
        if ax is None:
            fig, ax = plt.subplots()

        y_pct = self._percent_qe()
        ax.plot(self._wl, y_pct, **plot_kwargs)
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Quantum Efficiency (%)")
        ax.set_title("Detector QE vs Wavelength")
        if xlim is not None:
            ax.set_xlim(*xlim)
        ax.grid(True, which="both", alpha=0.3)
        return ax

    def correct(self, wavelengths: np.ndarray, counts: np.ndarray) -> np.ndarray:
        """
        Divide your counts by the interpolated quantum‐efficiency fraction
        at each wavelength so that:

            counts_true = counts_measured / QE(λ)
        """
        qe_at_meas = self._interp_qe(wavelengths)
        if np.any(qe_at_meas == 0):
            raise ValueError("Quantum efficiency is zero at some wavelengths; cannot correct.")
        return counts / qe_at_meas
