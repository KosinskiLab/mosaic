Geometry
========

.. currentmodule:: mosaic.geometry

The :class:`Geometry` class represents atomic geometry objects displayed in the VTK viewer, providing a unified interface for point clouds, orientations, and surface data with associated visualization properties.


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
   Geometry.model
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
   Geometry.is_mesh_representation


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
   Geometry.subset
   Geometry.get_point_data


Utility Functions
~~~~~~~~~~~~~~~~~

.. autosummary::
   :toctree: ../rst/

   Geometry.get_number_of_points


Serialization
~~~~~~~~~~~~~

The :class:`Geometry` class supports pickling for session persistence.

.. autosummary::
   :toctree: ../rst/

   Geometry.__getstate__
   Geometry.__setstate__


Indexing
~~~~~~~~

Geometry objects support array-like indexing using ``[]`` operator with integer indices, boolean masks, slices, or ellipsis. This creates a new :class:`Geometry` containing the subset of points.

.. code-block:: python

    # Select specific points by indices
    subset = geometry[[0, 1, 5, 10]]

    # Select points using boolean mask
    mask = geometry.points[:, 2] > 10.0
    subset = geometry[mask]

    # Create a full copy
    copy = geometry[...]


VolumeGeometry
==============

.. currentmodule:: mosaic.geometry

The :class:`VolumeGeometry` class extends Geometry to handle volumetric data with isosurface rendering capabilities for 3D volume visualization.


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
   VolumeGeometry.set_appearance


GeometryTrajectory
==================

.. currentmodule:: mosaic.geometry

The :class:`GeometryTrajectory` class handles time-series geometry data, enabling animation and temporal analysis of evolving geometric structures.


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
