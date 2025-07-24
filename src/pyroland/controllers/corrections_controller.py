"""
corrections_controller.py
=========================

Centralises the wavelength-dependent corrections that can be applied to a
spectrum.  Each individual correction lives in its own file; this controller
instantiates them, keeps track of which ones are *enabled*, and applies the
enabled set in a fixed, deterministic order.

Order of execution (chosen to mirror the original test script):

    1. Grating efficiency
    2. Fiber attenuation
    3. Camera quantum efficiency
    4. QTH-lamp lens transmission
    5. Silvered mirrors

The controller is intentionally independent of any UI code – it exposes
simple Python methods so that the Qt layer can remain thin.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List

import numpy as np

# --------------------------------------------------------------------------- #
# Individual correctors
# --------------------------------------------------------------------------- #
# NOTE: Each import is wrapped in a *fallback* so that the code still works
#       even if you renamed a class in your own module.  Change the class
#       names below if your local implementation differs.
try:
    from src.pyroland.corrections.correctors.grating_corrector import (
        GratingEfficiencyCorrector,
    )
except ImportError:  # pragma: no cover
    from src.pyroland.corrections.correctors.grating_corrector import (
        GratingCorrector as GratingEfficiencyCorrector,
    )

try:
    from src.pyroland.corrections.correctors.fiber_attenuation_corrector import (
        FiberAttenuationCorrector,
    )
except ImportError:  # pragma: no cover
    pass  # let the import fail loudly later if the file really is missing

try:
    from src.pyroland.corrections.correctors.camera_qe_efficiency_corrector import (
        QuantumEfficiencyCorrector,
    )
except ImportError:  # pragma: no cover
    from src.pyroland.corrections.correctors.camera_qe_efficiency_corrector import (
        CameraQEEfficiencyCorrector as QuantumEfficiencyCorrector,
    )

try:
    from src.pyroland.corrections.correctors.qth10_lamp_lens_corrector import (
        QTHLensTransmissionCorrector,
    )
except ImportError:  # pragma: no cover
    pass

try:
    from src.pyroland.corrections.correctors.spec_silv_mirror_corrector import (
        SilveredMirrorCorrection,
    )
except ImportError:  # pragma: no cover
    pass


# --------------------------------------------------------------------------- #
# Controller
# --------------------------------------------------------------------------- #
class CorrectionsController:
    """
    Maintains and applies a user-selectable set of spectral corrections.

    Parameters
    ----------
    base_data_dir
        Folder containing the CSV data files referenced by the correctors.
        If *None*, the folder ``<project-root>/corrections`` is assumed.
    fiber_length_m
        Length of the fibre patch cord in metres (used only by the
        :class:`~FiberAttenuationCorrector`).
    """

    # File names for the correction curves (relative to *base_data_dir*)
    _FILES = {
        "Grating efficiency (600 l/mm, 500 nm blaze)": "src/pyroland/corrections/data/grating_600lm_500nmBlaze_efficiency.csv",
        "Fiber attenuation (ThorLabs M59L02)": "src/pyroland/corrections/data/fiber_M59L02-attenuation.csv",
        "Camera QE (Newton DU920P_BX2DD)": "src/pyroland/corrections/data/camera_quantum_efficiency.csv",
        "Lens transmission (ThorLabs QTH10/M)": "src/pyroland/corrections/data/QTH_lamp_lens.csv",
        "Silvered mirrors (Andor Kymera 328i-D2-sil)": "src/pyroland/corrections/data/spectrometer_silvered-mirrors_reflectivity.csv",
    }

    # Fixed correction order (first → last)
    _ORDER: List[str] = [
        "Grating efficiency (600 l/mm, 500 nm blaze)",
        "Fiber attenuation (ThorLabs M59L02)",
        "Camera QE (Newton DU920P_BX2DD)",
        "Lens transmission (ThorLabs QTH10/M)",
        "Silvered mirrors (Andor Kymera 328i-D2-sil)",
    ]

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    def __init__(
        self,
        base_data_dir: str | Path | None = None,
        fiber_length_m: float = 2.0,
    ) -> None:
        self._base_dir = (
            Path(base_data_dir).resolve()
            if base_data_dir is not None
            else Path(__file__).resolve().parents[3]
        )

        # Instantiate each corrector with its CSV path
        self._correctors: Dict[str, object] = {
            "Grating efficiency (600 l/mm, 500 nm blaze)": GratingEfficiencyCorrector(
                str(self._base_dir / self._FILES["Grating efficiency (600 l/mm, 500 nm blaze)"])
            ),
            "Fiber attenuation (ThorLabs M59L02)": FiberAttenuationCorrector(
                str(self._base_dir / self._FILES["Fiber attenuation (ThorLabs M59L02)"]),
                fiber_length_m,
            ),
            "Camera QE (Newton DU920P_BX2DD)": QuantumEfficiencyCorrector(
                str(self._base_dir / self._FILES["Camera QE (Newton DU920P_BX2DD)"])
            ),
            "Lens transmission (ThorLabs QTH10/M)": QTHLensTransmissionCorrector(
                str(self._base_dir / self._FILES["Lens transmission (ThorLabs QTH10/M)"])
            ),
            "Silvered mirrors (Andor Kymera 328i-D2-sil)": SilveredMirrorCorrection(
                str(self._base_dir / self._FILES["Silvered mirrors (Andor Kymera 328i-D2-sil)"]),
                n_mirrors=3,
            ),
        }

        # Start with everything enabled
        self._enabled: Dict[str, bool] = {name: True for name in self._ORDER}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    # -- Introspection -------------------------------------------------- #
    def available_corrections(self) -> Iterable[str]:
        """Return the names of all known corrections (in execution order)."""
        return list(self._ORDER)

    def is_enabled(self, name: str) -> bool:
        """True if *name* is currently enabled."""
        return self._enabled.get(name, False)

    # -- Mutation ------------------------------------------------------- #
    def set_enabled(self, name: str, enabled: bool) -> None:
        """Enable or disable a single correction by *name*."""
        if name not in self._enabled:
            raise KeyError(f"Unknown correction: {name!r}")
        self._enabled[name] = bool(enabled)

    # -- Core functionality -------------------------------------------- #
    def apply(
        self,
        wavelengths_nm: np.ndarray,
        counts: np.ndarray,
    ) -> np.ndarray:
        """
        Apply all *enabled* corrections, returning a **new** array.

        The input arrays are **never** mutated.
        """
        corrected = counts.astype(float, copy=True)

        for name in self._ORDER:
            if self._enabled[name]:
                corrector = self._correctors[name]
                # Each corrector shares the same public API: ``correct(wl, counts)``
                corrected = corrector.correct(wavelengths_nm, corrected)

        return corrected
