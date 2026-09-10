Parametrization
===============

.. currentmodule:: mosaic.parametrization

The ``parametrization`` module provides abstract and concrete classes for representing point cloud surfaces as parametric models. These models support surface sampling, normal computation, and distance calculations.


Base Class
~~~~~~~~~~

.. autosummary::
   :toctree: rst
   :nosignatures:

   Parametrization


Geometric Shapes
~~~~~~~~~~~~~~~~

Parametric representations of simple geometric primitives.

.. autosummary::
   :toctree: rst

   Sphere
   Ellipsoid
   Cylinder
   RBF
   SplineCurve


Triangular Meshes
~~~~~~~~~~~~~~~~~

Surface representations using triangular mesh topology.

.. autosummary::
   :toctree: rst

   TriangularMesh
   BallPivoting
   PoissonMesh
   AlphaShape
   FlyingEdges


Utilities
~~~~~~~~~

Functions for combining and manipulating parametrization objects.

.. autosummary::
   :toctree: rst

   merge


Type Registry
~~~~~~~~~~~~~

The module provides a ``PARAMETRIZATION_TYPE`` dictionary that maps string identifiers to parametrization classes, enabling dynamic instantiation based on user selection.

.. code-block:: python

    from mosaic.parametrization import PARAMETRIZATION_TYPE

    # Available keys:
    # "sphere", "ellipsoid", "cylinder", "ball_pivoting",
    # "poisson", "rbf", "alpha_shape", "spline", "flying_edges"

    mesh_class = PARAMETRIZATION_TYPE["poisson"]
    mesh = mesh_class.fit(points, depth=8)
