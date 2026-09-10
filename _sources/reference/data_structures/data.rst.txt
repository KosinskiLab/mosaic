MosaicData
==========

.. currentmodule:: mosaic.data

:class:`MosaicData` is the central application-state object for the GUI.  It
wraps a headless :class:`~mosaic.commands.session.Session` with two
:class:`~mosaic.interactor.DataContainerInteractor` instances, one for point
clouds and one for fitted models, and coordinates between them.

Each instance carries the following attributes:

* ``data``: :class:`~mosaic.interactor.DataContainerInteractor` over the
  point-cloud container.
* ``models``: :class:`~mosaic.interactor.DataContainerInteractor` over the
  fitted-model container.
* ``active_picker``: name of the container currently bound to the area
  picker (``"data"`` or ``"models"``).
* ``shape``: bounding-box shape of the point-cloud workspace.


Constructor
~~~~~~~~~~~

.. autosummary::
   :toctree: ../rst/
   :nosignatures:

   MosaicData


File I/O
~~~~~~~~

.. autosummary::
   :toctree: ../rst/

   MosaicData.open_file
   MosaicData.to_file
   MosaicData.load_session
   MosaicData.reset


Interaction Modes
~~~~~~~~~~~~~~~~~

.. autosummary::
   :toctree: ../rst/

   MosaicData.activate_viewing_mode
   MosaicData.activate_picking_mode
   MosaicData.swap_area_picker
   MosaicData.highlight_clusters_from_selected_points


Visualization
~~~~~~~~~~~~~

.. autosummary::
   :toctree: ../rst/

   MosaicData.set_coloring_mode
   MosaicData.visibility_unselected
   MosaicData.refresh_lod
   MosaicData.refresh_actors


Session Hooks
~~~~~~~~~~~~~

Widgets can register callbacks that participate in session save/load by
contributing to the ``meta`` section of the session archive.

.. autosummary::
   :toctree: ../rst/

   MosaicData.register_session_hook


Utilities
~~~~~~~~~

.. autosummary::
   :toctree: ../rst/

   MosaicData.format_datalist
   MosaicData.get_tree_state
