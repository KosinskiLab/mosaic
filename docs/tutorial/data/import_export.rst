=================
Import and Export
=================

Importing Data
==============

Opening Files
-------------

- Select **File > Open** or press ``Ctrl+O``
- Select one or multiple files

A dialog window will open to configure how files are imported:

- **Scale Factor**: Multiplies coordinate values (default: ``1.0``)
- **Offset**: Subtracted from coordinates before scaling (default: ``0.0``)
- **Sampling Rate**: Physical distance between points (default: ``1.0``)

For multiple files, use **Next** and **Previous** to navigate, or **Apply to All** for identical settings.

Quick Tips
----------

- Access recent files via **File > Recent Files**
- For misoriented data, try negative scale factors
- Volume data sampling rate comes from file header
- Rename data to apppropriate extension

Exporting Data
==============

Export Types
------------

1. **Geometry**: Right-click on selected object(s) → **Export As**

   - **MRC**: Density maps (options: Shape X/Y/Z, Sampling)
   - **OBJ**: Triangular meshes
   - **TSV**: Points with orientation
   - **STAR**: Relion format (options: Shape X/Y/Z, Output Type)
   - **XYZ**: Simple coordinates

2. **Screenshots**:

   - Static: **File > Save Viewer Screenshot** (``Ctrl+P``)
   - Clipboard: Viewer only (``Ctrl+Shift+C``) or entire window (``Ctrl+Shift+W``)

3. **Animations**: **File > Export Animation** (``Ctrl+E``)

   - Configure: Animation Type, Format, Frame Rate, Range, Stride

4. **Sessions**: Save complete workspace

Export Tips
-----------

- Multi-object export: Some formats combine objects, others create separate files
- Set correct sampling rate to preserve scale
- Use base filename for batch export (saves as basefilename_index.extension)

Next Steps
==========

Continue to :doc:`sessions` to learn how to share mosaic sessions.