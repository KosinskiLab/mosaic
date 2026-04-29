Operations
==========

.. currentmodule:: mosaic.operations

The ``operations`` module provides a collection of geometry processing functions for point cloud and mesh manipulation. These operations handle common tasks like clustering, filtering, resampling, and surface fitting.

Decorator
~~~~~~~~~

.. autosummary::
   :toctree: rst

   use_point_data


Point Cloud Processing
~~~~~~~~~~~~~~~~~~~~~~

Operations for filtering, resampling, and extracting features from point clouds.

.. autosummary::
   :toctree: rst

   downsample
   remove_outliers
   skeletonize
   crop


Clustering
~~~~~~~~~~

Methods for partitioning point clouds into distinct groups.

.. autosummary::
   :toctree: rst

   cluster


Normal Computation
~~~~~~~~~~~~~~~~~~

Functions for calculating or modifying surface normals.

.. autosummary::
   :toctree: rst

   compute_normals


Surface Fitting
~~~~~~~~~~~~~~~

Operations for fitting parametric models and generating meshes from point clouds.

.. autosummary::
   :toctree: rst

   fit
   sample


Mesh Operations
~~~~~~~~~~~~~~~

Operations specific to triangular mesh processing.

.. autosummary::
   :toctree: rst

   remesh
   smooth


Utility Functions
~~~~~~~~~~~~~~~~~

General-purpose geometry utilities.

.. autosummary::
   :toctree: rst

   duplicate
   visibility


Operation Registry
~~~~~~~~~~~~~~~~~~

The :class:`GeometryOperations` class provides a central registry for all operation functions, allowing dynamic registration and access.

.. autosummary::
   :toctree: rst
   :nosignatures:

   GeometryOperations
