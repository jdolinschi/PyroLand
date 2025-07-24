# file: src/pyroland/controllers/corrections_info_controller.py
"""
corrections_info_controller.py
==============================

Display rich, user-friendly explanations (text + optional image) for each
available correction. The controller lazily builds and caches a dedicated
:class:`QDialog` per correction so that subsequent calls simply raise the
existing window instead of recreating it.

Extend the mapping returned by :meth:`_build_default_info_map` with your own
correction descriptions and illustrative images.

Author: Your Name <you@example.com>
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QScrollArea, QVBoxLayout, QWidget

logger = logging.getLogger(__name__)

class CorrectionsInfoController:
    """Manage and display information dialogs for spectrum corrections."""

    # Compute once: absolute path to the `resources/corrections` folder
    _RESOURCE_DIR = Path(__file__).parent.parent / "resources" / "corrections"

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    def __init__(self, parent=None) -> None:
        self._parent = parent
        self._dialogs: Dict[str, QDialog] = {}
        self._info_map: Dict[str, Tuple[str, Optional[Path]]] = self._build_default_info_map()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def show_info(self, correction_name: str) -> None:
        """Show an explanatory dialog for *correction_name*.

        If the dialog already exists, it is simply brought to the front.
        """
        if correction_name in self._dialogs:
            dlg = self._dialogs[correction_name]
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
            return

        description, image_path = self._info_for(correction_name)
        dlg = self._create_dialog(correction_name, description, image_path)
        self._dialogs[correction_name] = dlg
        dlg.show()

    # ------------------------------------------------------------------ #
    # Dialog construction helpers
    # ------------------------------------------------------------------ #
    def _create_dialog(
        self,
        title: str,
        description: str,
        image_path: Optional[Path],
    ) -> QDialog:
        dlg = QDialog(self._parent)
        dlg.setWindowTitle(f"{title} — Correction information")
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        scroll = QScrollArea(dlg)
        scroll.setWidgetResizable(True)

        content = QWidget()
        content_layout = QVBoxLayout(content)

        # Description text
        desc_label = QLabel(description, content)
        desc_label.setWordWrap(True)
        desc_label.setTextFormat(Qt.TextFormat.RichText)  # allow simple HTML
        content_layout.addWidget(desc_label)

        # Optional illustrative image
        if image_path:
            if image_path.is_file():
                pixmap = QPixmap(str(image_path))
                if not pixmap.isNull():
                    img_label = QLabel(content)
                    img_label.setAlignment(
                        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
                    )
                    # Downscale very wide images to fit nicely
                    max_width = 600
                    if pixmap.width() > max_width:
                        pixmap = pixmap.scaledToWidth(
                            max_width, Qt.TransformationMode.SmoothTransformation
                        )
                    img_label.setPixmap(pixmap)
                    content_layout.addWidget(img_label)
                else:
                    logger.warning("Failed to load pixmap from %s", image_path)
            else:
                logger.warning("Image file not found: %s", image_path)

        content_layout.addStretch()
        scroll.setWidget(content)

        layout = QVBoxLayout(dlg)
        layout.addWidget(scroll)

        dlg.resize(640, 480)
        return dlg

    # ------------------------------------------------------------------ #
    # Data helpers
    # ------------------------------------------------------------------ #
    def _info_for(self, name: str) -> Tuple[str, Optional[Path]]:
        """Return the info tuple for *name*, falling back to a placeholder."""
        return self._info_map.get(
            name,
            ("<p>No information available for this correction.</p>", None),
        )

    @classmethod
    def _build_default_info_map(cls) -> Dict[str, Tuple[str, Optional[Path]]]:
        """Return default mapping of correction names to (description, image)."""
        # Helper to resolve file under the resource directory
        def _img(name: str) -> Path:
            return cls._RESOURCE_DIR / name

        return {
            "Grating efficiency (600 l/mm, 500 nm blaze)": (
                """
                <h3>Grating efficiency correction</h3>
                <p>Diffraction gratings exhibit a wavelength-dependent efficiency, dispersing different colors of light 
                with varying effectiveness. To correct for this, we apply the manufacturer’s efficiency curve for the 
                600 lines/mm, 500 nm-blaze grating—sourced from Oxford Instruments’ resolution calculator 
                (https://andor.oxinst.com/tools/resolution-calculator)—to every measured wavelength in the Andor Kymera 
                328i. This ensures that the recorded spectrum is accurately adjusted according to the grating’s known 
                performance profile.</p>
                """,
                _img("Grating_efficiency_(600_lmm,_500_nm_blaze).png"),
            ),
            "Spectral response": (
                """
                <h3>Fiber attenuation (ThorLabs M59L02)</h3>
                <p>Fiber optic cables attenuate light at different </p>
                """,
                _img("spectral_response.png"),
            ),
        }
