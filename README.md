# Mosaic

[![Build Status](https://img.shields.io/github/actions/workflow/status/KosinskiLab/mosaic/main.yml?label=CI)](https://github.com/KosinskiLab/mosaic/actions)
[![PyPI](https://img.shields.io/pypi/v/mosaic-gui.svg)](https://pypi.org/project/mosaic-gui/)
[![License: GPL v2](https://img.shields.io/badge/License-GPL_v2-blue.svg)](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html)

**[Documentation](https://kosinskilab.github.io/mosaic/)** | **[Installation](https://kosinskilab.github.io/mosaic/tutorial/installation.html)**


Mosaic is a software ecosystem that translates 3D electron microscopy (3D EM) data into simulation-ready models of biomembranes. It unifies membrane segmentation, mesh generation, protein identification, and multi-scale simulation into a graphical user interface (GUI).

![Mosaic Workflow](docs/_static/tutorial/iav_workflow/mosaic_workflow.png)

## Quick Start

Mosaic requires Python 3.11 or higher.

```bash
pip install mosaic-gui
mosaic &
```

For detailed installation instructions, see our [Installation Guide](https://kosinskilab.github.io/mosaic/tutorial/installation.html).


## How to Cite

If you use Mosaic in your research, please [cite](https://www.biorxiv.org/content/10.1101/2025.05.24.655915v1):

```bibtex
@article{Maurer2025.05.24.655915,
	author = {Maurer, Valentin J. and Siggel, Marc and Jensen, Rasmus K. and Mahamid, Julia and Kosinski, Jan and Pezeshkian, Weria},
	journal = {bioRxiv},
	title = {Helfrich Monte Carlo Flexible Fitting: physics-based, data-driven cell-scale simulations},
	doi = {10.1101/2025.05.24.655915},
	year = {2025}
}
```