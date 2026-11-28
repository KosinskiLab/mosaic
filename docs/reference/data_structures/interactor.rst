DataContainerInteractor
=======================

.. currentmodule:: mosaic.interactor

:class:`DataContainerInteractor` mediates between a
:class:`~mosaic.container.DataContainer` and its tree widget. It manages
selection and edits for one container. :class:`~mosaic.data.MosaicData` holds
two of them, ``data`` for point clouds and ``models`` for fitted models. Both
share a :class:`~mosaic.viewport.ViewportInteractor`.


Constructor
~~~~~~~~~~~

.. autosummary::
   :toctree: ../rst/
   :nosignatures:

   DataContainerInteractor


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


Geometry Operations
~~~~~~~~~~~~~~~~~~~

The ribbon runs processing operations such as clustering and downsampling
through :class:`~mosaic.operations.GeometryOperations` on the selected
geometries.

.. autosummary::
   :toctree: ../rst/

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
