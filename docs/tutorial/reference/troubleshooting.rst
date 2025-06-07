===============
Troubleshooting
===============

This page provides solutions for common issues encountered when using Mosaic.

File Import Errors
------------------

**Symptoms:**

- "Unsupported format" error
- "Invalid file" or parsing errors
- Empty or partial data loaded

**Solutions:**

1. Verify file format matches the extension
2. Check file for corruption or incomplete data
3. Try opening in another application first
4. For text formats, check for encoding issues (use UTF-8)
5. Check header format for specialized formats (MRC, STAR)

**Common Format Issues:**

- **Missing header**: Some formats require specific headers
- **Wrong byte order**: Binary formats may need endian conversion
- **Text encoding**: Use UTF-8 for text formats
- **Line endings**: Some parsers are sensitive to CR/LF differences


Performance Issues
------------------

**Symptoms:**

- Slow response when rotating or zooming
- Long processing times for operations
- High memory usage

**Solutions:**

1. Reduce point size for large point clouds
2. Hide complex objects when not needed
3. Use simpler representation modes
4. Reduce number of objects by removing or merging

**Recommended File Size Limits:**

- Point clouds: 5 million on laptop 10-20 million with GPU
- Meshes: 5-10 million triangles
- Volumes: 512³ voxels

**For larger files:**

- Consider using **Downsample** in the **Segmentation** tab
- Process data in smaller chunks
- Use more powerful hardware


Selection Problems
------------------

**Symptoms:**

- Can't select points or objects
- Selection works inconsistently
- Wrong objects selected

**Solutions:**

1. Check current interaction mode (bottom status bar)
2. Press ``s`` to switch between cluster and model objects
3. Try different selection methods (area vs. point selection)
4. Verify picking tolerance in preferences
5. Ensure objects are visible

Crashes During Operations
-------------------------

**Symptoms:**

- Application crashes during specific operations
- "Not responding" status
- Operation never completes

**Solutions:**

1. Save your work frequently
2. Try the operation on a smaller subset of data
3. For operations such as curvature computation, ensure meshes are valid
4. Check system memory availability
5. Restart Mosaic if it becomes unresponsive

Export Failures
---------------

**Symptoms:**

- Error messages during export
- Incomplete or corrupted output files
- "Permission denied" errors

**Solutions:**

1. Check write permissions for target directory
2. Verify disk space is sufficient
3. Try a different output format
4. Export to a local drive rather than network location
5. Close any applications that might be using the target file

Missing Features in Exported Files
----------------------------------

**Symptoms:**

- Exported files lack expected data
- Missing colors, normals, or metadata
- Geometry issues in exported models

**Solutions:**

1. Check if the target format supports all required features
2. Configure export options to include needed attributes
3. Consider using a more comprehensive format (OBJ instead of STL)
4. Verify that source data contains the expected attributes

Session Won't Load
------------------

**Symptoms:**

- Error message when loading session
- "Incompatible version" warnings
- Partial or corrupted session state

**Solutions:**

1. Verify you're using the same Mosaic version that created the session
2. Check if external files referenced by the session still exist
3. For cross-version loading, try export/import individual objects instead
4. Check session file integrity and size
5. Try loading on the same operating system where it was created

Mesh Generation Failures
------------------------

**Symptoms:**

- Mesh creation fails or produces poor results
- Holes, artifacts, or incorrect topology
- Error messages during mesh operations

**Solutions:**

1. Try different mesh generation methods:

   - Alpha Shape for simple surfaces
   - Ball Pivoting for structured data
   - Poisson for watertight meshes

2. Adjust method-specific parameters
3. Clean input point cloud (remove outliers)
4. Increase point density in sparse areas
5. For complex shapes, segment into simpler parts first
