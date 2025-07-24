from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QScrollArea, QVBoxLayout, QWidget

logger = logging.getLogger(__name__)

class CorrectionsInfoController:
    """Manage and display information dialogs for spectrum corrections.

    Each correction entry can include multiple illustrative images. The first
    image is displayed above the description, any others are shown below.
    """

    # Absolute path to the `resources/corrections` folder
    _RESOURCE_DIR = Path(__file__).parent.parent / "resources" / "corrections"

    def __init__(self, parent=None) -> None:
        self._parent = parent
        self._dialogs: Dict[str, QDialog] = {}
        # Map: correction name -> (HTML description, list of image Paths)
        self._info_map: Dict[str, Tuple[str, List[Path]]] = self._build_default_info_map()

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

        description, image_paths = self._info_for(correction_name)
        dlg = self._create_dialog(correction_name, description, image_paths)
        self._dialogs[correction_name] = dlg
        dlg.show()

    def _create_dialog(
        self,
        title: str,
        description: str,
        image_paths: List[Path],
    ) -> QDialog:
        """Construct a scrollable dialog with optional images above and below text."""
        dlg = QDialog(self._parent)
        dlg.setWindowTitle(f"{title} — Correction information")
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        scroll = QScrollArea(dlg)
        scroll.setWidgetResizable(True)

        content = QWidget()
        content_layout = QVBoxLayout(content)

        # If there's at least one image, show the first above the description
        if image_paths:
            self._add_image_widget(content_layout, image_paths[0])

        # Description text (rich HTML)
        desc_label = QLabel(description, content)
        desc_label.setWordWrap(True)
        desc_label.setTextFormat(Qt.TextFormat.RichText)
        content_layout.addWidget(desc_label)

        # Show any remaining images below the description
        for img_path in image_paths[1:]:
            self._add_image_widget(content_layout, img_path)

        content_layout.addStretch()
        scroll.setWidget(content)

        layout = QVBoxLayout(dlg)
        layout.addWidget(scroll)
        dlg.resize(900, 1024)
        return dlg

    def _add_image_widget(self, layout: QVBoxLayout, image_path: Path) -> None:
        """Helper to load and insert a QPixmap into the given layout."""
        if not image_path:
            return
        if image_path.is_file():
            pixmap = QPixmap(str(image_path))
            if not pixmap.isNull():
                img_label = QLabel()
                img_label.setAlignment(
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
                )
                # Downscale very wide images to fit the dialog
                max_width = 600
                if pixmap.width() > max_width:
                    pixmap = pixmap.scaledToWidth(
                        max_width, Qt.TransformationMode.SmoothTransformation
                    )
                img_label.setPixmap(pixmap)
                layout.addWidget(img_label)
            else:
                logger.warning("Failed to load pixmap from %s", image_path)
        else:
            logger.warning("Image file not found: %s", image_path)

    def _info_for(self, name: str) -> Tuple[str, List[Path]]:
        """Return the info (description and image list) for *name* or a placeholder."""
        return self._info_map.get(
            name,
            ("<p>No information available for this correction.</p>", []),
        )

    @classmethod
    def _build_default_info_map(cls) -> Dict[str, Tuple[str, List[Path]]]:
        """Return default mapping of correction names to (description, list of images)."""
        def _img(name: str) -> Path:
            return cls._RESOURCE_DIR / name

        return {
            "Grating efficiency (600 l/mm, 500 nm blaze)": (
                # HTML description
                """
                <h3>Grating efficiency correction</h3>
                <p>Diffraction gratings exhibit a wavelength-dependent efficiency, dispersing different colors of light 
                with varying effectiveness. To correct for this, we apply the manufacturer’s efficiency curve for the 
                600 lines/mm, 500 nm-blaze grating—sourced from Oxford Instruments’ resolution calculator 
                (https://andor.oxinst.com/tools/resolution-calculator)—to every measured wavelength in the Andor Kymera 
                328i. This ensures that the recorded spectrum is accurately adjusted according to the grating’s known 
                performance profile.</p>
                """,
                [
                    _img("600lmm_500nm_grating_image.png"),
                    _img("Grating_efficiency_(600_lmm,_500_nm_blaze).png"),
                ],
            ),
            "Fiber attenuation (ThorLabs M59L02)": (
                """
                <h3>Fiber attenuation</h3>
                <p>Fiber optic cables attenuate light at different wavelengths. We apply the measured attenuation 
                spectrum provided by ThorLabs for the M59L02 (2 m) fiber to correct intensity variations across our 
                spectral range.</p>
                """,
                [
                    _img("Thorlabs_M59L02_image.jpg"),
                    _img("Fiber_optic_cable_attenuation_(ThorLabs_M59L02_-_2_m).png"),
                ],
            ),
            "Camera QE (Newton DU920P_BX2DD)": (
                """
                <h3>CCD camera quantum efficiency</h3>
                <p>CCD sensors exhibit a wavelength-dependent quantum efficiency (QE), defined as the ratio of photoelectrons generated to incident photons. 
                By applying the QE curve specific to the Newton DU920P_BX2DD, we correct for the sensor’s varying sensitivity across the spectrum, ensuring that each measured wavelength is accurately normalized to the camera’s photon-to-electron conversion performance.</p>
                """,
                [
                    _img("newton_920P_image.png"),
                    _img("CCD_camera_QE_(Newton_DU920P_BX2DD).png"),
                ],
            ),
            "Lens transmission (ThorLabs QTH10/M)": (
                """
                <h3>Lens transmission correction</h3>
                <p>Lenses exhibit wavelength-dependent transmission based on their glass type and any anti-reflection coatings. 
                To correct for this, we apply the manufacturer’s transmission curve for the ThorLabs QTH10/M lens—specifying the percentage of light transmitted at each wavelength—ensuring the recorded spectrum is adjusted for the lens’s known throughput characteristics.</p>
                """,
                [
                    _img("qth10m_lens_image.png"),
                    _img("Lens_transmittance_(Installed_in_ThorLabs_QTH10M).png"),
                ],
            ),
            "Silvered mirrors (Andor Kymera 328i-D2-sil)": (
                """
                <h3>Silvered mirror reflectance correction</h3>
                <p>Silvered mirrors exhibit wavelength-dependent reflectance influenced by the coating and substrate. 
                The Andor Kymera 328i-D2-sil includes four such mirrors, but depending on the optical path and configuration, 
                light may reflect off three before detection. To account for this, we apply the cumulative reflectance curve 
                for three reflections—sourced from Oxford Instruments—to correct the measured spectrum for mirror losses at each wavelength.</p>
                """,
                [
                    _img("andor-kymera-mirrors-image.png"),
                    _img("Mirror_reflectance_(3_used_in_the_Andor_Kymera_328i).png"),
                ],
),


        }
