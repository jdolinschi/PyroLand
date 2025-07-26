# Pyroland  :fire: Spectroscopy & Pyrometry GUI

[![GitHub release](https://img.shields.io/github/v/release/jdolinschi/pyroland)](https://github.com/jdolinschi/pyroland/releases/latest)
[![License](https://img.shields.io/github/license/jdolinschi/pyroland)](https://github.com/jdolinschi/pyroland/blob/main/LICENSE)
![Python](https://img.shields.io/badge/python-3.9–3.13-blue)

**Pyroland** is a cross-platform desktop application that loads Andor `.sif`
spectra automatically by actively watching a folder for new files,
applies wavelength-dependent corrections (grating efficiency, fiber
attenuation, camera QE, etc.) that is specific to our set-up, 
and plots calibrated spectra or pyrometric temperature fits automatically.
You can add calibrations for your specific optical lay out by following the pattern in 
the calibrations' folder.

To get info on each specific calibration that comes preloaded, just double-click the calibration 
in the table.

Supports fitting specific regions of the data either through tail and head masking of the spectrum 
or an unlimited number of specific x-regions within the spectrum. For example, if you have extra peaks 
within the spectrum, you can filter them out with the excluded regions table by adding a new region and entering the x-min 
and x-max of the spectrum to not use for fitting.

---

## Features

* **Five built-in corrections**  
  Grating efficiency, fiber attenuation, quantum efficiency, QTH-lamp lens
  transmission, and silvered-mirror reflectance.
* **Live preview** — enable/disable each correction and see the effect instantly.
* **Temperature fitting** with gray body fitting.
* **Spectrum masking** either through a global min-max or specific regions within the spectrum.
* **High-resolution export** to PNG or save to a `.asc` file.
* Written in **PySide 6** (Qt) — looks native on Windows, macOS, and Linux.

<div align="center">
  <img src="docs/screenshot.png" width="700">
</div>

---

## Quick start (Windows)

| Option                      | Steps                                                                                                                   | Requires Python? |
|-----------------------------|-------------------------------------------------------------------------------------------------------------------------|------------------|
| **1. One-click EXE** (easy) | 1. Download **Pyroland-1.0.0.exe** from the [Releases] page.<br>2. Double-click.                                        | **No** |
| **3. poetry / developers**  | ```powershell\npgit clone https://github.com/jdolinschi/PyroLand\ncd pyroland\npoetry install\npoetry run pyroland\n``` | **Yes** (3.9 – 3.13) |

> **Updating**  
> • EXE users: download the new file from Releases.  
> • poetry users: `git pull && poetry install --sync`.

---