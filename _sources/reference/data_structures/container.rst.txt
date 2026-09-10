DataContainer
=============

.. currentmodule:: mosaic.container

The :class:`DataContainer` class manages collections of geometry objects, providing operations for manipulation, analysis, and visualization of point cloud data. It serves as the core data structure for organizing clusters and models within the Mosaic application.


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
   DataContainer.get
   DataContainer.update
   DataContainer.clear
   DataContainer.get_actors


UUID Resolution
~~~~~~~~~~~~~~~

Geometries in the container are identified by unique UUIDs, allowing stable references even as indices change.

.. autosummary::
   :toctree: ../rst/

   DataContainer.uuid_to_index


Visualization Control
~~~~~~~~~~~~~~~~~~~~~

.. autosummary::
   :toctree: ../rst/

   DataContainer.highlight
   DataContainer.highlight_points
   DataContainer.update_appearance


Container Length
~~~~~~~~~~~~~~~~

The container supports the ``len()`` function to get the number of stored geometries:

.. code-block:: python

    container = DataContainer()
    container.add(points1)
    container.add(points2)
    print(len(container))  # Output: 2
