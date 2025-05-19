==========
Quickstart
==========

This quickstart guide will help you get up and running with Mosaic, providing the minimal steps needed to load data, visualize it, and save your work.

Loading Data
============

1. Launch Mosaic by running ``mosaic`` from your terminal or command prompt.

2. Once the application opens, click on **File > Open** or use the shortcut ``Ctrl+O`` to bring up the file selection dialog.

3. Navigate to your data file and select it. Mosaic supports various formats including:

   - MRC, MAP, EM (volume segmentation data)
   - OBJ, PLY, STL (mesh data)
   - TSV, STAR (point cloud data with angular orientation, e.g. protein picks)
   - XYZ, CSV, TXT (point cloud data)

4. After selecting a file, the Import Parameters dialog will appear, allowing you to set:

   - Scale: Controls the overall size scaling
   - Offset: Shifts the data position
   - Sampling Rate: Defines the resolution/spacing

   #Screenshot: Import Parameters dialog

5. Click **OK** to load the data. Your data will appear in the 3D viewport and be listed in the Object Browser panel.


Basic Interaction
=================

Navigating the 3D View
----------------------

- Rotate: Click and drag with the left mouse button
- Pan: Hold Shift and drag with the left mouse button
- Zoom: Use the mouse wheel

Standard Camera Views
---------------------

For standard orientations, use the keyboard shortcuts:

- ``X``: View along X axis
- ``Z``: View along Z axis
- ``C``: View along Y axis

Selecting and Managing Objects
------------------------------

1. Click on items in the Object Browser to select them
2. Use Ctrl+click to select multiple items, Ctrl+A for all items, Ctrl+Shift for a from-to selection.
3. Right-click objects to access their context menu with operations like:

   - Show / Hide
   - Duplicate / Remove
   - Change representation
   - Export
   - Properties

   #Screenshot: Context menu on an object

Making a Simple Selection
-------------------------

For interacting with points in an object:

- Press ``R`` to activate the rubber band selection tool
- Click and drag in the 3D viewport to select points
- Press ``E`` to expand selection to entire clusters

For selecting an entire object press ``S`` to activate the picking mode. For switching from interacting with clusters to models press ``s``.


Saving Your Work
================

Save a Screenshot
-----------------

To save a screenshot of the 3D viewport:

1. Select **File > Save Viewer Screenshot** or press ``Ctrl+P``
2. Choose a location and filename

Save a Session
--------------

To save your entire workspace for later use:

1. Select **File > Save Session** or press ``Ctrl+S``
2. Choose a location and filename (with .pickle extension)
3. This will save all your data, models, and view settings


Next Steps
==========

With these basic operations, you can already start exploring your data in Mosaic. For more detailed functionality, continue to the :doc:`Concepts and UI <concepts>` section.