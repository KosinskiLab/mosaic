Geometry
========

.. currentmodule:: mosaic.geometry

The `Geometry` class represents atomic geometry objects displayed in the VTK viewer, providing a unified interface for point clouds, orientations, and surface data with associated visualization properties.

Constructor
~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/
   :nosignatures:

   Geometry

Core Data Properties
~~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   Geometry.points
   Geometry.normals
   Geometry.quaternions
   Geometry.sampling_rate
   Geometry.actor
   Geometry.visible

Visualization Control
~~~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   Geometry.set_color
   Geometry.set_visibility
   Geometry.set_appearance
   Geometry.change_representation

Point Coloring
~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   Geometry.color_points
   Geometry.set_scalars

Data Manipulation
~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   Geometry.swap_data
   Geometry.merge

Utility Functions
~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   Geometry.get_number_of_points
   Geometry.compute_distance


VolumeGeometry
==============
.. currentmodule:: mosaic.geometry

The `VolumeGeometry` class extends Geometry to handle volumetric data with isosurface rendering capabilities for 3D volume visualization.

Constructor
~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/
   :nosignatures:

   VolumeGeometry

Volume Operations
~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   VolumeGeometry.update_isovalue
   VolumeGeometry.update_isovalue_quantile


GeometryTrajectory
==================
.. currentmodule:: mosaic.geometry

The `GeometryTrajectory` class handles time-series geometry data, enabling animation and temporal analysis of evolving geometric structures.

Constructor
~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/
   :nosignatures:

   GeometryTrajectory

Trajectory Control
~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   GeometryTrajectory.frames
   GeometryTrajectory.display_frame