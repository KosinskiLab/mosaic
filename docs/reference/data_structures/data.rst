MosaicData
==========
.. currentmodule:: mosaic.data

The `MosaicData` class serves as the central application state manager for the Mosaic GUI, coordinating between point cloud data (clusters) and geometric models while handling user interactions and maintaining the overall workspace state.

Constructor
~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/
   :nosignatures:

   MosaicData

Core Data Containers
~~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   MosaicData.data
   MosaicData.models
   MosaicData.shape

User Interaction Management
~~~~~~~~~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   MosaicData.active_picker
   MosaicData.swap_area_picker
   MosaicData.activate_viewing_mode
   MosaicData.toggle_picking_mode
   MosaicData.highlight_clusters_from_selected_points

Session Persistence
~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   MosaicData.to_file
   MosaicData.load_session

Utilities
~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   MosaicData.format_datalist
