DataContainerInteractor
=======================

.. currentmodule:: mosaic.interactor

The `DataContainerInteractor` class mediates between the GUI interface and underlying DataContainer, handling user interactions, visual representation, and data operations within the Mosaic application's 3D viewport.

Constructor
~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/
   :nosignatures:

   DataContainerInteractor

Core Interface Components
~~~~~~~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   DataContainerInteractor.data_list
   DataContainerInteractor.container
   DataContainerInteractor.vtk_widget

Interaction Modes
~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   DataContainerInteractor.attach_area_picker
   DataContainerInteractor.activate_viewing_mode
   DataContainerInteractor.toggle_drawing_mode
   DataContainerInteractor.toggle_picking_mode

Selection Management
~~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   DataContainerInteractor.set_selection
   DataContainerInteractor.deselect
   DataContainerInteractor.deselect_points
   DataContainerInteractor.highlight_selected_points
   DataContainerInteractor.highlight_clusters_from_selected_points

Point Cloud Operations
~~~~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   DataContainerInteractor.cluster
   DataContainerInteractor.remove_outliers
   DataContainerInteractor.decimate
   DataContainerInteractor.downsample
   DataContainerInteractor.crop_cluster
   DataContainerInteractor.trim

Cluster Management
~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   DataContainerInteractor.merge_cluster
   DataContainerInteractor.duplicate
   DataContainerInteractor.remove_cluster
   DataContainerInteractor.split_cluster

Visualization Control
~~~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   DataContainerInteractor.change_visibility
   DataContainerInteractor.toggle_visibility
   DataContainerInteractor.change_representation
   DataContainerInteractor.render
   DataContainerInteractor.render_vtk

Data Import/Export
~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   DataContainerInteractor.add
   DataContainerInteractor.cluster_points
   DataContainerInteractor.remove_points

Utility Functions
~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   DataContainer