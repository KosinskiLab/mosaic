.. include:: ../substitutions.rst


Installation
------------

.. _installation-section:

We recommend creating an installation enviroment for a clean and isolated setup. Available options for different use cases are outlined in the tabs below.

.. tab-set::

   .. tab-item:: Venv

      Venv is Python's built-in virtual environment module. Venv is a good choice for simpler setups, but does not handle non-Python dependencies.

      .. code-block:: bash

         python3 -m venv mosaic
         source mosaic/bin/activate

   .. tab-item:: Conda

      Conda is a powerful package manager that creates isolated environments with both Python and non-Python dependencies. Conda is a good choice for more complex setups and cross-platform compatibility.

      .. code-block:: bash

         conda create --name mosaic -c conda-forge python=3.11

After setting up your environment, |project| can be installed from PyPi

.. code-block:: bash

   pip install mosaic["all"]

.. tip::

   Use the following to install |project| without optional dependencies

   .. code-block:: bash

      pip install mosaic


DTS simulations
---------------

If you intend to use features of |project| that pertain to DTS simulations, you also need to install FreeDTS for simulation and Trimem for mesh equilibration.

FreeDTS can be installed by following the instructions in https://github.com/weria-pezeshkian/FreeDTS. Alternatively, we provide a python wrapper that can be installed using pip

.. code-block:: bash

   pip install pyfreedts

Trimem can be installed by following the instructions in the repository https://github.com/bio-phys/trimem

.. code-block:: bash

   git clone --recurse-submodules https://github.com/bio-phys/trimem.git
   pip install trimem/


DTS Backmapping
---------------

We use TS2CG (https://github.com/weria-pezeshkian/TS2CG-v2.0) to map back meshes onto coarse-grained representations for molecular dynamics simulations and Martinize2 (https://github.com/marrink-lab/vermouth-martinize) to create the corresponding coarse-grained representations of atomic structures. Both can be intalled using pip

.. code-block:: bash

   pip install TS2CG
   pip install vermouth


Development
-----------

The latest development version can be installed from GitHub

.. code-block:: bash

   pip install git+https://github.com/KosinskiLab/mosaic.git

If you want to modify the codebase

.. code-block:: bash

   git clone https://github.com/KosinskiLab/mosaic.git
   poetry install mosaic
