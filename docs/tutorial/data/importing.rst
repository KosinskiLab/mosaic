=================
Importing Data
=================

This section covers how to import data into Mosaic and configure import parameters.

Opening Files
============
1. Select **File > Open** or press ``Ctrl+O``
2. Navigate to your data file
3. Select one or multiple files
4. Click **Open**

#Screenshot: File Open dialog

Import Parameters Dialog
=======================
After selecting files, configure how each file is imported:

#Screenshot: Import Parameters dialog

Scale Factor
-----------
Multiplies all coordinate values. Use for:
- Adjusting size to match other items
- Converting between units
- Correcting scale issues

Default: ``1.0``

Offset
------
Subtracted from coordinates before scaling. Use for:
- Centering data
- Aligning multiple datasets
- Removing unwanted shifts

Default: ``0.0``

Sampling Rate
------------
Defines physical distance between points. Crucial for:
- Distance measurements
- Filtering parameters
- Scale-dependent operations

Default: ``1.0``

Importing Multiple Files
-----------------------
1. Configure parameters for the first file
2. Use **Next →** and **← Previous** to navigate between files
3. For identical settings, click **Apply to All**
4. Click **Accept**

#Screenshot: Import dialog with Apply to All button

Recent Files
===========
Access recently opened files:
- Select **File > Recent Files**
- Choose a file from the submenu

Import Tips
==========

Coordinate Systems
----------------
If data appears incorrectly oriented:
- Try negative scale factors (e.g., ``-1.0``)
- Check alignment from different view orientations
- Verify coordinate system handedness

File Format Detection
-------------------
If a file has a non-standard extension:
- Rename with the appropriate extension
- Or specify the format in the file dialog

Volume Data Import
----------------
For volume data:
- Sampling rate comes from the file header
- MRC sampling rate = voxel size in Ångstroms
- Origin offset is applied automatically

Next Steps
=========
After importing data:
- View :doc:`volumes` for volumetric data
- Use the Segmentation tab for point cloud operations
- Try the Parametrization tab for model fitting

Continue to :doc:`exporting` to learn how to export data.