Formats
=======
.. currentmodule:: mosaic.formats

The `formats` module provides comprehensive file I/O capabilities for various scientific data formats commonly used in microscopy and structural biology.

Core Functions
~~~~~~~~~~~~~~
.. autosummary::
   :toctree: rst

   open_file
   open_session

Data Container Classes
~~~~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: rst
   :nosignatures:

   DataObject
   DataContainer

Writers
~~~~~~~
.. autosummary::
   :toctree: rst

   OrientationsWriter
   write_density

Parser
======
.. currentmodule:: mosaic.formats.parser

The `parser` module handles loading and processing of density maps and volumetric data from various file formats.

Density Loading
~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: rst

   load_density

Volume Processing
~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: rst

   mrc_to_pointcloud
   volume_to_pointcloud