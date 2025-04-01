===============
Concepts and UI
===============

This section introduces the fundamental concepts behind Mosaic and explains the main components of the user interface.

Core Concepts
============

Data Organization
----------------

Mosaic organizes data into two main categories:

1. **Clusters** (Data points): Raw point cloud data, typically representing segmented structures
2. **Models** (Fits): Parametric or mesh representations that provide mathematical descriptions of structures

These two types of data are displayed in separate lists in the Object Browser. Each entry shows:

- Visibility status
- Object Type (icon)
- Name (editable)

Right-clicking an item opens a context menu with operations specific to that object type.

#Screenshot: Object Browser showing Clusters and Models with context menu open


Coordinate System
---------------

Mosaic uses a right-handed coordinate system:

- X-axis: Horizontal (left to right)
- Y-axis: Vertical (bottom to top)
- Z-axis: Depth (back to front)

The standard orientation is (0, 0, 1).


Sampling Rate
------------

Mosaic does not handle spatial units internally. Instead, imported data is immediately transformed into a consistent reference frame based on the sampling rate (typically Ångstroms for molecular data). This sampling rate is provided by the user or can be extracted from the header of particular file formats, e.g. 'mrc' files.

Assuming a segmentation is loaded from an 'mrc' file with a sampling rate of 6.80 Ångstroms per voxel, Mosaic will multiply the voxel coordinates with the sampling rate. Therefore, the internal scale would be in Ångstroms. The sampling rate also affects:

- Display size
- Filtering operations
- Distance measurements
- Export operations

.. note::

   Backmapping triangulated meshes onto coarse-grained models implicitly assumes the internal reference frame to be Ångstroms.


UI Layout
=========

The Mosaic interface consists of several key components:

#Screenshot: Annotated main window showing all components

1. **Menu Bar**: Access to file operations, view settings and help
2. **Tab Bar**: Switches between major functional areas
3. **Ribbon Toolbar**: Context-specific tools for the active tab
4. **Object Browser**: Lists and manages loaded data with:
   - Visibility indicators (colored dots)
   - Editable names
   - Point counts or types
   - Context menus for operations
5. **3D Viewport**: Main visualization area with:
   - Navigation controls
   - Orientation indicators
   - Optional coordinate axes
6. **Property Panel**: Shows properties of selected objects
7. **Volume Viewer** (optional): Controls for volume data display
8. **Status Bar**: Shows application status and activates optional panels


Functional Tabs
--------------

Mosaic organizes functionality into three main tabs:

1. **Segmentation**: Tools for working with point cloud data (clustering, filtering, selection) and analysing object properties
2. **Parametrization**: Tools for fitting and working with models (geometric fitting, mesh operations)
3. **Intelligence**: Advanced features (Dynamically Triangulated Surface simulations, constrained template matching, membrane segmentations)

#Screenshot: Ribbon toolbar with functional tabs visible


Interaction Modes
===============

Mosaic supports several interaction modes that change how mouse actions affect the 3D view:

1. **Viewing Mode** (default): Rotate, pan and zoom the camera
2. **Switch Interaction** (``s``): Switch from interacting with cluster to model objects.
3. **Selection Mode** (``R``): Select points using a rubber band
4. **Drawing Mode** (``A``): Add points to the selected cluster
5. **Curve Mode** (``Shift+A``): Create curves and press ``Enter`` to save the curve as points.
6. **Picking Mode** (``S``): Select objects by clicking on them
7. **Mesh Edit Mode** (``q``): Select and remove triangles from meshes.
8. **Mesh Add Mode** (``Q``): Connect mesh vertices to add new triangles.

Switching between modes will change the cursor appearance. The current mode is displayed in the **Status Bar**. To exit any mode and return to Viewing Mode press the same button again.

Keyboard Shortcuts
================

Navigation
---------

- ``Z``, ``X``, ``C``: Set camera view along Z, X, or Y axes
- ``V``: Swap camera view direction
- ``D``: Toggle renderer background color

Selection and Manipulation
------------------------

- ``A``: Toggle drawing mode
- ``R``: Toggle area selector
- ``P``: Toggle picking mode
- ``S``: Swap selector between Clusters and Models
- ``M``: Merge selected clusters
- ``Delete``: Remove selected clusters or points
- ``E``: Expand selection

File Operations
-------------

- ``Ctrl+N``: New session
- ``Ctrl+O``: Import files
- ``Ctrl+S``: Save session
- ``Ctrl+P``: Save screenshot
- ``Ctrl+Shift+P``: Save screenshot to clipboard
- ``Ctrl+E``: Export animation
- ``Ctrl+H``: Show keybinds

Next Steps
=========

Now that you understand the basic concepts and layout of Mosaic, proceed to the :doc:`Working with Data <data/importing>` section to learn how to handle different data types.
