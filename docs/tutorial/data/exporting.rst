=================
Exporting Data
=================

This section explains how to export data from Mosaic for use in other applications.

Export Options
=============
Mosaic provides four export types:
1. **Geometry Export**: Point clouds, meshes, and models
2. **Volume Export**: Voxel-based representations
3. **Image Export**: Screenshots and animations
4. **Session Export**: Complete workspaces

Exporting Geometry
=================
1. Select objects in the Object Browser
2. Right-click on a selected object
3. Choose **Export As** from the context menu
4. Select the desired format
5. Configure format-specific options if needed
6. Choose a save location and filename

#Screenshot: Context menu showing Export As option

Available Formats
----------------
- **MRC**: Export as density map
- **OBJ**: Export triangular meshes
- **TSV**: Export points with orientation information
- **STAR**: Export in Relion format
- **XYZ**: Export simple coordinate files

Format-Specific Options
---------------------

MRC Options
^^^^^^^^^^
- **Shape X/Y/Z**: Output volume dimensions
- **Sampling**: Voxel size

STAR Options
^^^^^^^^^^
- **Shape X/Y/Z**: Reference volume dimensions
- **Output Type**: Relion format version

Exporting Screenshots
====================

Static Screenshots
----------------
1. Select **File > Save Viewer Screenshot** or press ``Ctrl+P``
2. Choose format and location (PNG for transparency)
3. Click **Save**

Clipboard Screenshots
------------------
- **Viewer only**: Press ``Ctrl+Shift+C``
- **Entire window**: Press ``Ctrl+Shift+W``

Exporting Animations
==================
1. Select **File > Export Animation** or press ``Ctrl+E``
2. Configure:
   - **Animation Type**: Trajectory, Slices, or Reveal
   - **Format**: MP4, AVI, or PNG frames
   - **Frame Rate**, **Range**, and **Stride**

#Screenshot: Animation Settings dialog

Export Tips
==========

Multi-Object Export
-----------------
- Formats supporting multiple objects (MRC, STAR, TSV): Objects combine
- Single-object formats (OBJ, XYZ): Separate numbered files

Preserving Scale
--------------
- Set correct sampling rate during import
- Verify MRC voxel size matches expected units

Batch Export
----------
1. Select all objects to export
2. Export with a base filename
3. Objects save as basefilename_index.extension

Command Line Export
-----------------
For automated workflows:

.. code-block:: bash

   mosaic --export input.pickle --format mrc --output output.mrc

Next Steps
=========
Learn how to manage sessions in the :doc:`sessions` section.