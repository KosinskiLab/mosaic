ViewportInteractor
==================

.. currentmodule:: mosaic.viewport

:class:`ViewportInteractor` manages VTK interaction and rendering for the
point-cloud and fitted-model panes. Access it through ``MosaicData.viewport``.

.. autoclass:: ViewportInteractor


Interaction Modes and Selection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use :meth:`ViewportInteractor.set_mode` with a
:class:`~mosaic.widgets.ViewerModes` value to change how the pointer interacts
with the active pane. The ``current_target`` attribute identifies that pane.

.. autosummary::
   :toctree: ../rst/

   ViewportInteractor.set_mode
   ViewportInteractor.set_target
   ViewportInteractor.swap_target
   ViewportInteractor.highlight_clusters_from_selected_points


Visualization
~~~~~~~~~~~~~

.. autosummary::
   :toctree: ../rst/

   ViewportInteractor.set_coloring_mode
   ViewportInteractor.visibility_unselected
   ViewportInteractor.refresh_lod
   ViewportInteractor.render
