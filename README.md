# Mosaic

[![Build Status](https://img.shields.io/github/actions/workflow/status/KosinskiLab/mosaic/main.yml?label=CI)](https://github.com/KosinskiLab/mosaic/actions)
[![PyPI](https://img.shields.io/pypi/v/mosaic-gui.svg)](https://pypi.org/project/mosaic-gui/)
[![License: GPL v2](https://img.shields.io/badge/License-GPL_v2-blue.svg)](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html)

**[Documentation](https://kosinskilab.github.io/mosaic/)** | **[Installation](https://kosinskilab.github.io/mosaic/tutorial/installation.html)**

## Why Mosaic?

Biological membranes define cellular compartments and orchestrate signaling cascades, all while undergoing constant remodeling. We can resolve their structure from imaging data, but the analysis path is fragmented. One tool for segmentation, another for meshing, something else for protein localization, yet another for setting up physical simulations. Export, convert, hope nothing breaks.

Mosaic fixes that. One graphical interface for the entire workflow.

Ask questions and get answers immediately. What is the membrane curvature where proteins cluster? How does protein density vary across the surface? How would this system behave under different conditions? Explore interactively and transition seamlessly from observation to quantitative hypothesis testing to data-driven physical simulations of real geometries.


## What You Can Do

Import tomograms, segment membranes, build surface meshes, localize proteins, measure geometry, export simulation-ready systems. Adjust parameters and watch results update in real time.

<p align="center">
  <a href="https://kosinskilab.github.io/mosaic/tutorial/workflows/iav.html">
    <img src="docs/_static/tutorial/iav_workflow/mosaic_workflow.png" alt="Mosaic Workflow" width="600">
  </a>
</p>

<p align="center"><em>Complete influenza A virus analysis: from tomogram to simulation-ready model</em></p>

**See it work:** The [IAV tutorial](https://kosinskilab.github.io/mosaic/tutorial/workflows/iav.html) walks through a real analysis start to finish. About 30 minutes hands-on.

Need to prep for MD? Export Martini-compatible coarse-grained systems with positioned proteins. Run HMFF to refine membrane shapes using both your experimental density and physics. Send the result straight to GROMACS.

<p align="center">
  <img src="docs/_static/tutorial/mosaic_overview.png" alt="Mosaic GUI Interface" width="700">
</p>
<p align="center"><em>Mosaic interface</em></p>


Once your workflow is dialed in, use the pipeline builder to scale it:

```bash
mosaic-pipeline config.json
```

## Installation

Mosaic requires Python 3.11 or higher. Install with pip:

```bash
pip install mosaic-gui
mosaic &
```

The graphical interface launches immediately. For advanced installation options see the [installation guide](https://kosinskilab.github.io/mosaic/tutorial/installation.html).

## Citation

If Mosaic contributes to your research, please [cite](https://www.biorxiv.org/content/10.1101/2025.05.24.655915v1):

```bibtex
@article{Maurer2025,
  author = {Maurer, Valentin J. and Siggel, Marc and Jensen, Rasmus K. and
            Mahamid, Julia and Kosinski, Jan and Pezeshkian, Weria},
  title = {Helfrich Monte Carlo Flexible Fitting: physics-based,
           data-driven cell-scale simulations},
  journal = {bioRxiv},
  year = {2025},
  doi = {10.1101/2025.05.24.655915}
}
```

Mosaic and HMFF were developed jointly to bridge structural data and physical simulations. HMFF uniquely integrates experimental volumetric data into membrane simulations, enabling data and physics to jointly determine membrane conformation. HMFF is implemented in [FreeDTS](https://github.com/weria-pezeshkian/FreeDTS/wiki/User-Manual-for-version-2) and integrated into Mosaic.

---

## About

Mosaic is developed by the [Kosinski Lab](https://www.embl.org/groups/kosinski/) at the European Molecular Biology Laboratory (EMBL Hamburg).

**License:** GPL-2.0 (see [LICENSE](LICENSE) for details)

## Links

- **Documentation**: https://kosinskilab.github.io/mosaic/
- **PyPI Package**: https://pypi.org/project/mosaic-gui/
- **Source Code**: https://github.com/KosinskiLab/mosaic
- **Issues & Support**: https://github.com/KosinskiLab/mosaic/issues
