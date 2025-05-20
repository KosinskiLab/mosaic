============
Installation
============

.. include:: ../substitutions.rst

Before installing Mosaic, ensure your system meets the following requirements.

Prerequisites
-------------

- **Python**: 3.11+ (3.11 recommended)
- **Operating System**:

  - Linux (recommended)
  - macOS (some performance limitations noted below)
  - Windows 10+ (not tested but principally supported)
- **Hardware**:

  - Standard consumer laptops (8GB RAM recommended)
  - NVIDIA GPU with CUDA support required for: membrane segmentation, template matching and molecular dynamics simulations (oldest model tested: RTX 3090)

.. note::
   macOS Users: Due to compatibility issues, some functions (edge length-based remeshing and certain parametrizations) have reduced performance compared to Linux systems, but yield the same output.


Installation
------------

.. _installation-section:

We recommend creating a virtual environment for a clean and isolated setup.

.. tab-set::

   .. tab-item:: Venv

      Python's built-in option, suitable for simpler setups.

      .. code-block:: bash

         python3 -m venv mosaic
         source mosaic/bin/activate

   .. tab-item:: Conda

      Best for cross-platform compatibility and managing complex dependencies.

      .. code-block:: bash

         conda create --name mosaic -c conda-forge python=3.11
         conda activate mosaic

After setting up your environment, Mosaic can be installed from PyPI

.. code-block:: bash

   pip install "mosaic[all]"
   mosaic --version          # Smoke test to verify installation


Optional Dependencies
---------------------

Mosaic provides specialized functionality through the following optional components.

.. _installation-dts:

DTS Simulations
^^^^^^^^^^^^^^^

If you intend to use Mosaic for dynamically triangulated surface (DTS) simulations, please install these additional tools

**FreeDTS**: Can be installed by following the instructions at https://github.com/weria-pezeshkian/FreeDTS. Alternatively, use our Python wrapper:

.. code-block:: bash

   pip install pyfreedts

**Trimem**: Install from the repository at https://github.com/bio-phys/trimem:

.. code-block:: bash

   git clone --recurse-submodules https://github.com/bio-phys/trimem.git
   pip install trimem/

.. _installation-backmapping:

DTS Backmapping
^^^^^^^^^^^^^^^

If you intend to use Mosaic for creating coarse-grained representations of meshes, install TS2CG (https://github.com/weria-pezeshkian/TS2CG-v2.0) for backmapping and Martinize2 (https://github.com/marrink-lab/vermouth-martinize) for creating coarse-grained representations of atomic structures

.. code-block:: bash

   pip install TS2CG vermouth

We use Gromacs for equilibrating coarse-grained Martini models. The installation instructions are available `here <https://manual.gromacs.org/current/install-guide/index.html>`_.


Instructions for Developers
---------------------------

The latest development version of Mosaic can be installed from GitHub

.. code-block:: bash

   pip install git+https://github.com/KosinskiLab/mosaic.git

If you want to modify the codebase

.. code-block:: bash

   pip install poetry
   git clone https://github.com/KosinskiLab/mosaic.git
   cd mosaic
   poetry install


Getting Help
------------

- Check the :doc:`troubleshooting guide <reference/troubleshooting>`.
- Open an issue on :doc:`GitHub <reference/issues>`.
