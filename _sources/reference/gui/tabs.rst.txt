Tabs
====
.. currentmodule:: mosaic.tabs

The `tabs` module implements the main functional areas of the Mosaic GUI, each providing specialized tools and workflows.

Main Tab Classes
~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/
   :nosignatures:

   SegmentationTab
   ModelTab
   IntelligenceTab

Segmentation Operations
~~~~~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   SegmentationTab.show_ribbon
   PlaneTrimmer
   ClusterTransformer

Modeling Operations
~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   ModelTab.show_ribbon

Intelligence Operations
~~~~~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   IntelligenceTab.show_ribbon

Interaction Styles
==================
.. currentmodule:: mosaic.styles

The `styles` module provides specialized VTK interaction styles for advanced 3D editing and curve creation workflows.

Mesh Editing
~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/
   :nosignatures:

   MeshEditInteractorStyle

Curve Creation
~~~~~~~~~~~~~~
.. autosummary::
   :toctree: ../rst/

   CurveBuilderInteractorStyle