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

   DataContainer.data
   DataContainer.metadata
   DataContainer.add
   DataContainer.remove
   DataContainer.get_actors
   DataContainer.get_cluster_count
   DataContainer.get_cluster_size

Collection Operations
~~~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   DataContainer.merge
   DataContainer.duplicate
   DataContainer.split
   DataContainer.new

Point Cloud Processing
~~~~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   DataContainer.decimate
   DataContainer.downsample
   DataContainer.crop
   DataContainer.trim
   DataContainer.sample

Clustering and Analysis
~~~~~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   DataContainer.connected_components
   DataContainer.dbscan_cluster
   DataContainer.remove_outliers

Visualization Control
~~~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   DataContainer.highlight
   DataContainer.highlight_points
   DataContainer.change_visibility
   DataContainer.update_appearance

Selection Management
~~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   DataContainer.add_selection