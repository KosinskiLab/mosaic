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
   DataContainerInteractor.merge
   DataContainerInteractor.remove


Geometry Operations
~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   DataContainerInteractor.cluster
   DataContainerInteractor.remove_outliers
   DataContainerInteractor.decimate
   DataContainerInteractor.downsample
   DataContainerInteractor.crop_cluster
   DataContainerInteractor.trim
   DataContainerInteractor.duplicate


Visualization Control
~~~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   DataContainerInteractor.change_visibility
   DataContainerInteractor.toggle_visibility
   DataContainerInteractor.change_representation
   DataContainerInteractor.render
   DataContainerInteractor.render_vtk
