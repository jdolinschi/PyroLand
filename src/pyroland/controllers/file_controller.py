"""
file_controller.py
==================

Responsible solely for serialising *one* spectrum, its fit and all associated
metadata to a human-readable ``.asc`` text file.

All heavy lifting is done here so that `MainController` can stay focussed on
UI duties.

Author: Your Name <you@example.com>
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

__all__ = ["FileController"]


class FileController:
    """Utility class – **all methods are static**."""

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    @staticmethod
    def save(
        save_path: Path,
        wavelengths_nm: np.ndarray,
        counts: np.ndarray,
        fit_result: Optional[Dict[str, Any]],
        sif_info: Any,
        global_xmin: Optional[float],
        global_xmax: Optional[float],
        excluded_regions: List[Tuple[float, float]],
        corrections_state: Dict[str, bool],
        overwrite: bool = True,
    ) -> None:
        """
        Build the ``.asc`` file content and write it to *save_path*.

        Parameters
        ----------
        save_path
            Destination filename (the ``.asc`` extension is enforced).
        wavelengths_nm / counts
            1-D arrays containing the raw spectrum.
        fit_result
            Dictionary returned by ``TemperatureController.fit`` (may be *None*).
        sif_info
            The ``_info`` object returned by ``sif_parser.parse`` (dict, list or str).
        global_xmin / global_xmax
            Current fitting range limits (may be *None*).
        excluded_regions
            List of ``(xmin, xmax)`` pairs.
        corrections_state
            Mapping of *correction name* → *True/False* (enabled?).
        overwrite
            If *False* and file exists, raises ``FileExistsError`` instead.
        """
        save_path = save_path.with_suffix(".asc")
        if save_path.exists() and not overwrite:
            raise FileExistsError(f"{save_path} already exists")

        # ------------------------------------------------------------------ #
        # Header: fit statistics
        # ------------------------------------------------------------------ #
        header_lines: List[str] = []
        if fit_result:
            header_lines.extend(
                _kv_lines(
                    temperature=fit_result.get("T"),
                    temperature_error=fit_result.get("T_err"),
                    S=fit_result.get("S"),
                    S_error=fit_result.get("S_err"),
                    R2=fit_result.get("r2") or fit_result.get("gof"),
                )
            )
        else:
            header_lines.append("temperature: n/a")
            header_lines.append("temperature_error: n/a")
            header_lines.append("S: n/a")
            header_lines.append("S_error: n/a")
            header_lines.append("R2: n/a")

        # ------------------------------------------------------------------ #
        # SIF metadata
        # ------------------------------------------------------------------ #
        header_lines.append("")  # blank line separator
        header_lines.append("# --- SIF metadata ---")
        header_lines.extend(_normalise_info(sif_info))

        # ------------------------------------------------------------------ #
        # Global range
        # ------------------------------------------------------------------ #
        header_lines.append("# --- Global range ---")
        header_lines.extend(_kv_lines(global_xmin=global_xmin, global_xmax=global_xmax))

        # ------------------------------------------------------------------ #
        # Excluded regions
        # ------------------------------------------------------------------ #
        header_lines.append("# --- Excluded regions ---")
        if excluded_regions:
            for idx, (xmin, xmax) in enumerate(excluded_regions, start=1):
                header_lines.extend(
                    _kv_lines(**{f"excluded_region_{idx}_xmin": xmin,
                                 f"excluded_region_{idx}_xmax": xmax})
                )
        else:
            header_lines.append("excluded_regions: none")

        # ------------------------------------------------------------------ #
        # Corrections
        # ------------------------------------------------------------------ #
        header_lines.append("# --- Corrections applied ---")
        for name, state in corrections_state.items():
            header_lines.append(f"{name}: {state}")

        # ------------------------------------------------------------------ #
        # Raw spectrum
        # ------------------------------------------------------------------ #
        spectrum_lines: List[str] = ["", "# --- Spectrum data ---",
                                     "wavelength_nm,count"]
        for wl, ct in zip(wavelengths_nm, counts):
            spectrum_lines.append(f"{wl},{ct}")

        # ------------------------------------------------------------------ #
        # Write to disk
        # ------------------------------------------------------------------ #
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text("\n".join(header_lines + spectrum_lines), encoding="utf-8")


# ------------------------------------------------------------------------- #
# Helper functions (private)
# ------------------------------------------------------------------------- #
def _kv_lines(**kwargs) -> List[str]:
    """Return ``name: value`` lines, skipping *None* values."""
    return [f"{k}: {v}" for k, v in kwargs.items() if v is not None]


def _normalise_info(info: Any) -> List[str]:
    """
    Convert *info* returned from ``sif_parser`` into ``key: value`` lines.

    Supports dicts, sequences of pairs, sequences of strings or plain strings.
    Unknown types are coerced via ``str``.
    """
    if info is None:
        return ["info: n/a"]

    lines: List[str] = []
    if isinstance(info, dict):
        for k, v in info.items():
            lines.append(f"{k}: {v}")
    elif isinstance(info, (list, tuple)):
        for entry in info:
            if isinstance(entry, (list, tuple)) and len(entry) == 2:
                k, v = entry
                lines.append(f"{k}: {v}")
            else:
                lines.append(str(entry))
    else:
        lines.append(str(info))
    return lines
