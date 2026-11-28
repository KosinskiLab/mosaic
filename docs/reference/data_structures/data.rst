MosaicData
==========

.. currentmodule:: mosaic.data

:class:`MosaicData` is the central application-state object for the GUI.  It
wraps a headless :class:`~mosaic.commands.session.Session` with two
:class:`~mosaic.interactor.DataContainerInteractor` instances and a shared
:class:`~mosaic.viewport.ViewportInteractor`.

Each instance provides these attributes.

* ``data`` is the interactor for the point-cloud container.
* ``models`` is the interactor for the fitted-model container.
* ``viewport`` manages interaction modes, picking, and rendering for both containers.
* ``shape`` is the bounding-box shape of the point-cloud workspace.


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


Visualization
~~~~~~~~~~~~~

.. autosummary::
   :toctree: ../rst/

   MosaicData.refresh_lod


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
