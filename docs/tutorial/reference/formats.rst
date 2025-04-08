=====================
File Format Reference
=====================

This page documents all file formats supported by Mosaic, their specifications, and usage details.

Volume Formats
==============

MRC (.mrc, .map)
----------------
- **Type**: Binary
- **Description**: Standard format for electron microscopy density maps
- **Header**: Contains voxel size, grid dimensions, origin coordinates
- **Byte Order**: Machine-dependent, typically little-endian
- **Data Types**: 8-bit, 16-bit, 32-bit, float
- **Specification**: http://www.ccpem.ac.uk/mrc_format/mrc2014.php

EM (.em)
--------
- **Type**: Binary
- **Description**: IMAGIC EM format for microscopy data
- **Header**: 512 bytes header with dimensions and metadata
- **Data Types**: 8-bit, 16-bit, 32-bit float

HDF5 (.h5)
----------
- **Type**: Binary hierarchical container
- **Description**: General-purpose scientific data format
- **Structure**: Groups, datasets, and attributes
- **Data Types**: Supports all primitive types
- **Compression**: Supports various compression methods

Point Cloud Formats
===================

XYZ (.xyz)
----------
- **Type**: ASCII text
- **Structure**: Three columns (X, Y, Z coordinates) per line
- **Optional**: Fourth column for cluster ID
- **Header**: None required, but can contain comment lines
- **Example**:
  ```
  1.234 5.678 9.012
  2.345 6.789 0.123
  ```

CSV (.csv)
----------
- **Type**: ASCII text
- **Delimiter**: Comma (,)
- **Structure**: X,Y,Z[,ID] per line
- **Header**: Optional first line with column names

TSV (.tsv)
----------
- **Type**: ASCII text
- **Delimiter**: Tab character
- **Structure**: X\tY\tZ[\tID] per line
- **Header**: Optional first line

Mesh Formats
============

OBJ (.obj)
----------
- **Type**: ASCII text
- **Structure**: Lists of vertices, faces and normals
- **Prefix**: 'v' for vertices, 'f' for faces, 'vn' for normals
- **Example**:
  ```
  v 1.0 0.0 0.0
  v 0.0 1.0 0.0
  v 0.0 0.0 1.0
  f 1 2 3
  ```

PLY (.ply)
----------
- **Type**: ASCII or binary
- **Description**: Stanford polygon format
- **Header**: Defines element types and counts
- **Data**: Vertices and faces with properties
- **Example Header**:
  ```
  ply
  format ascii 1.0
  element vertex 3
  property float x
  property float y
  property float z
  element face 1
  property list uchar int vertex_indices
  end_header
  ```

STL (.stl)
----------
- **Type**: ASCII or binary
- **Description**: Simple triangulated surfaces
- **Structure**: Triangle normals and vertices
- **Binary Format**: 80-byte header, 4-byte triangle count, 50 bytes per triangle

Orientation Formats
===================

STAR (.star)
------------
- **Type**: ASCII text
- **Description**: Relion data format for particle metadata
- **Structure**: Header with column definitions followed by data
- **Key Columns**:
  - _rlnCoordinateX, _rlnCoordinateY, _rlnCoordinateZ
  - _rlnAngleRot, _rlnAngleTilt, _rlnAnglePsi
- **Example**:
  ```
  data_
  loop_
  _rlnCoordinateX #1
  _rlnCoordinateY #2
  _rlnCoordinateZ #3
  _rlnAngleRot #4
  _rlnAngleTilt #5
  _rlnAnglePsi #6
  100.0 200.0 300.0 45.0 90.0 0.0
  ```

CIF (.cif)
----------
- **Type**: ASCII text
- **Description**: Crystallographic Information File format
- **Structure**: Data blocks with loop definitions
- **Domain**: Atomic structures with positions and orientations

Trajectory Formats
==================

TSI (.tsi, .q)
--------------
- **Type**: ASCII text
- **Description**: Topology files with time series data
- **Structure**: Version, box dimensions, vertices, faces
- **Example**:
  ```
  version 1.1
  box 100.0 100.0 100.0
  vertex 1000
  1 10.0 20.0 30.0
  ...
  triangle 1500
  3 0 1 2
  ...
  ```

VTU (.vtu)
----------
- **Type**: XML-based
- **Description**: VTK unstructured grid files
- **Structure**: Points, cells, and data arrays
- **Features**: Supports cell and point data attributes

Session Format
==============

Pickle (.pickle)
----------------
- **Type**: Binary
- **Description**: Python serialization format
- **Content**: Complete Mosaic session with all objects
- **Compatibility**: Python version dependent
- **Security**: Only open pickles from trusted sources

Troubleshooting
===============

Invalid Format Issues
---------------------
- **Missing header**: Some formats require specific headers
- **Wrong byte order**: Binary formats may need endian conversion
- **Text encoding**: Use UTF-8 for text formats
- **Line endings**: Some parsers are sensitive to CR/LF differences

Large File Handling
-------------------
- Maximum recommended file sizes:
  - Point clouds: 10-20 million points
  - Meshes: 5-10 million triangles
  - Volumes: 512³ voxels
- For larger files, consider using downsampling

See Also
========
:doc:`../data/import_export` for import and export options