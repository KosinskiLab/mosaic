Widgets
=======
.. currentmodule:: mosaic.widgets

The `widgets` module provides specialized GUI components for 3D visualization, data interaction, and user interface elements within the Mosaic application.

Core Interface Components
~~~~~~~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/
   :nosignatures:

   ObjectBrowserSidebar
   RibbonToolBar
   ContainerListWidget
   StyledListWidgetItem

3D Visualization Widgets
~~~~~~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   AxesWidget
   BoundingBoxManager
   ScaleBarWidget
   LegendWidget

Volume and Time-series
~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: VolumeViewer

.. autosummary::
   :toctree: ../rst/

   TrajectoryPlayer

Interaction Control
~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   ViewerModes
   CursorModeHandler
   StatusIndicator

Ribbon Utilities
~~~~~~~~~~~~~~~~

Use ``RibbonToolBar.add_section`` to group ribbon buttons.

.. autosummary::
   :toctree: ../rst/

   create_button
