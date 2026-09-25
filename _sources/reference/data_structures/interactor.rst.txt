DataContainerInteractor
=======================

.. currentmodule:: mosaic.interactor

:class:`DataContainerInteractor` mediates between a
:class:`~mosaic.container.DataContainer` and the GUI: it owns the VTK pickers,
the tree-widget representation of the container, and the geometry operations
exposed in the ribbon.  :class:`~mosaic.data.MosaicData` holds two of them,
``data`` for point clouds and ``models`` for fitted models.


Constructor
~~~~~~~~~~~

.. autosummary::
   :toctree: ../rst/
   :nosignatures:

   DataContainerInteractor


Interaction Modes
~~~~~~~~~~~~~~~~~

The interactor switches between three pointer modes (viewing, drawing, and
picking) and owns the area picker used for box selection.

.. autosummary::
   :toctree: ../rst/

   DataContainerInteractor.attach_area_picker
   DataContainerInteractor.activate_viewing_mode
   DataContainerInteractor.activate_drawing_mode
   DataContainerInteractor.activate_picking_mode


Selection
~~~~~~~~~

.. autosummary::
   :toctree: ../rst/

   DataContainerInteractor.get_selected_geometries
   DataContainerInteractor.set_selection_by_uuid
   DataContainerInteractor.deselect
   DataContainerInteractor.deselect_points
   DataContainerInteractor.highlight_selected_points
   DataContainerInteractor.highlight_clusters_from_selected_points


Data Management
~~~~~~~~~~~~~~~

.. autosummary::
   :toctree: ../rst/

   DataContainerInteractor.add
   DataContainerInteractor.add_selection
   DataContainerInteractor.merge
   DataContainerInteractor.remove
   DataContainerInteractor.update
   DataContainerInteractor.undo


Geometry Operations
~~~~~~~~~~~~~~~~~~~

These methods are dispatched to :class:`~mosaic.operations.GeometryOperations`
via the operation registry. They apply the named operation to every selected
geometry, optionally as a background task.

.. autosummary::
   :toctree: ../rst/

   DataContainerInteractor.cluster
   DataContainerInteractor.skeletonize
   DataContainerInteractor.downsample
   DataContainerInteractor.remove_outliers
   DataContainerInteractor.compute_normals
   DataContainerInteractor.duplicate
   DataContainerInteractor.visibility


Visualization
~~~~~~~~~~~~~

.. autosummary::
   :toctree: ../rst/

   DataContainerInteractor.next_color
   DataContainerInteractor.set_coloring_mode
   DataContainerInteractor.change_representation
   DataContainerInteractor.render
   DataContainerInteractor.render_vtk
   DataContainerInteractor.refresh_actors
