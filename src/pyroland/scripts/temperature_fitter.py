import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit


class TemperatureFitter:
    """
    Fit a corrected spectrum to a blackbody (Planck) curve and extract temperature.

    Model:
        I(λ; T, S) = S * (c1 / λ^5) * 1 / (exp(c2 / (λ T)) - 1)

    where:
        λ in meters,
        T in Kelvin,
        S is a unit‑conversion/scaling factor,
        c1 = 3.7418e-16 W·m^2,
        c2 = 0.014388   m·K.
    """

    # Physical constants
    _c1 = 3.7418e-16  # W·m^2
    _c2 = 0.014388  # m·K

    @staticmethod
    def _planck(wl_m, T, S):
        """Black‑body spectral radiance vs wavelength (m)."""
        # avoid division by zero
        exponent = TemperatureFitter._c2 / (wl_m * T)
        return S * (TemperatureFitter._c1 / wl_m ** 5) / (np.exp(exponent) - 1)

    def __init__(self, p0=(2000, 1e-11), title="Black-body Fit"):
        """
        Parameters
        ----------
        p0 : tuple (T_guess, S_guess)
            Initial guesses for temperature (K) and scale.
        """
        self.gof = None
        self.gof_label = None
        self._p0 = p0
        self.T = None
        self.T_err = None
        self.S = None
        self.S_err = None
        self.title = title

    def fit(self, wavelengths_nm: np.ndarray, counts: np.ndarray,
            yerr: np.ndarray | None = None, plot: bool = True):
        """
        Fit the input spectrum and (optionally) plot data+fit.

        Parameters
        ----------
        wavelengths_nm : array-like
            Wavelengths in nanometers.
        counts : array-like
            Measured (fully corrected) counts.
        plot : bool
            If True, produces a matplotlib plot of data and fit.

        Returns
        -------
        T_fit, T_err : tuple of floats
            Best‑fit black‑body temperature (K) and its 1σ uncertainty.
        """
        # Convert wavelengths to meters
        wl_m = wavelengths_nm * 1e-9

        sigma = yerr if yerr is not None else None

        popt, pcov = curve_fit(
            self._planck,
            wl_m,
            counts,
            p0=self._p0,
            sigma=sigma,
            absolute_sigma=(yerr is not None),
            maxfev=100000
        )

        T_fit, S_fit = popt
        perr = np.sqrt(np.diag(pcov))
        T_err, S_err = perr

        # Store
        self.T, self.T_err = T_fit, T_err
        self.S, self.S_err = S_fit, S_err

        # --- Goodness of fit ---
        model = self._planck(wl_m, T_fit, S_fit)
        resid = counts - model

        if yerr is not None:
            chi2 = np.sum((resid / yerr) ** 2)
            dof = counts.size - len(popt)
            gof_value = chi2 / dof
            gof_label = r'$\chi^2_\nu$'
        else:
            ss_res = np.sum(resid ** 2)
            ss_tot = np.sum((counts - np.mean(counts)) ** 2)
            gof_value = 1 - ss_res / ss_tot
            gof_label = r'$R^2$'

        self.gof = gof_value
        self.gof_label = gof_label

        # Plot if desired
        if plot:
            # Raw data
            plt.figure()
            plt.plot(wavelengths_nm, counts, 'o', ms=4, label='Data')
            # Overplot fit
            wl_fit = np.linspace(wavelengths_nm.min(),
                                 wavelengths_nm.max(), 500)
            I_fit = self._planck(wl_fit * 1e-9, T_fit, S_fit)
            plt.plot(wl_fit, I_fit, '-', lw=2,
                     label=(f'Black‑body fit (T = {T_fit:.0f}±{T_err:.0f} K, '
                            f'{gof_label} = {gof_value:.3f})')
                     )
            plt.xlabel('Wavelength (nm)')
            plt.ylabel('Counts (arb. units)')
            plt.title(self.title)
            plt.legend()
            plt.tight_layout()
            plt.grid(True)
            plt.show()

        return T_fit, T_err, S_fit, S_err, gof_value
