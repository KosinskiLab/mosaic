DataContainer
=============
.. currentmodule:: mosaic.container

The `DataContainer` class manages collections of geometry objects, providing operations for manipulation, analysis, and visualization of point cloud data. It serves as the core data structure for organizing clusters and models within the Mosaic application.

Constructor
~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/
   :nosignatures:

   DataContainer

Data Access and Management
~~~~~~~~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   DataContainer.add
   DataContainer.remove
   DataContainer.get_actors
   DataContainer.get_cluster_size


Visualization Control
~~~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   DataContainer.highlight
   DataContainer.highlight_points
   DataContainer.update_appearance
