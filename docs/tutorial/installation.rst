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


Development
-----------

The latest development version can be installed from GitHub

.. code-block:: bash

   pip install git+https://github.com/KosinskiLab/mosaic.git

If you want to modify the codebase

.. code-block:: bash

   git clone https://github.com/KosinskiLab/mosaic.git
   poetry install mosaic
