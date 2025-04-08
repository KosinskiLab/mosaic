=======================
Configuration Reference
=======================

Mosaic can be configured through configuration files and settings. This page documents all available options and their effects.

Configuration Files
===================

Location
--------

Mosaic reads configuration from the following locations (in order of precedence):

1. Command-line specified config (``--config file.cfg``)
2. Project-specific config (``.mosaic.cfg`` in the current directory)
3. User config (``~/.config/mosaic/config.cfg`` or ``%APPDATA%\Mosaic\config.cfg``)
4. System-wide config (``/etc/mosaic/config.cfg`` or ``C:\ProgramData\Mosaic\config.cfg``)

Format
------

Configuration files use the INI format:

.. code-block:: ini

   [section]
   option = value
   another_option = another_value

   [another_section]
   option = value

General Settings
================

[General]
---------

.. list-table::
   :widths: 30 20 50
   :header-rows: 1

   * - Option
     - Default
     - Description
   * - ``language``
     - ``en``
     - Interface language (en, de, fr, etc.)
   * - ``theme``
     - ``system``
     - UI theme (system, light, dark)
   * - ``recent_files_count``
     - ``10``
     - Number of recent files to remember
   * - ``autosave``
     - ``true``
     - Enable automatic session saving
   * - ``autosave_interval``
     - ``600``
     - Seconds between autosaves
   * - ``autosave_location``
     - ``~/.cache/mosaic/autosave``
     - Directory for autosave files
   * - ``confirm_exit``
     - ``true``
     - Show confirmation dialog on exit

[Performance]
-------------

.. list-table::
   :widths: 30 20 50
   :header-rows: 1

   * - Option
     - Default
     - Description
   * - ``max_threads``
     - ``auto``
     - Maximum number of threads (auto = CPU count)
   * - ``cache_size``
     - ``2048``
     - Memory cache size in MB
   * - ``point_limit``
     - ``5000000``
     - Warning threshold for point count
   * - ``mesh_limit``
     - ``1000000``
     - Warning threshold for mesh triangle count
   * - ``volume_limit``
     - ``512,512,512``
     - Maximum volume dimensions
   * - ``use_gpu``
     - ``true``
     - Enable GPU acceleration when available

[Display]
---------

.. list-table::
   :widths: 30 20 50
   :header-rows: 1

   * - Option
     - Default
     - Description
   * - ``background_color``
     - ``#1a1a1a``
     - 3D view background color
   * - ``alt_background_color``
     - ``#ffffff``
     - Alternative background color
   * - ``point_size``
     - ``8``
     - Default point size
   * - ``default_opacity``
     - ``1.0``
     - Default object opacity
   * - ``ambient_light``
     - ``0.3``
     - Ambient light intensity
   * - ``diffuse_light``
     - ``0.7``
     - Diffuse light intensity
   * - ``specular_light``
     - ``0.2``
     - Specular light intensity
   * - ``axes_visible``
     - ``true``
     - Show coordinate axes

Visualization Settings
======================

[Colors]
--------

.. list-table::
   :widths: 30 20 50
   :header-rows: 1

   * - Option
     - Default
     - Description
   * - ``default_color``
     - ``#b3b3b3``
     - Default object color
   * - ``highlight_color``
     - ``#cc3333``
     - Selection highlight color
   * - ``model_color``
     - ``#3366cc``
     - Default model color
   * - ``colormap``
     - ``viridis``
     - Default colormap for property visualization

[Volume]
--------

.. list-table::
   :widths: 30 20 50
   :header-rows: 1

   * - Option
     - Default
     - Description
   * - ``default_colormap``
     - ``gray``
     - Default colormap for volume display
   * - ``projection_enabled``
     - ``false``
     - Enable projection by default
   * - ``default_orientation``
     - ``z``
     - Initial slice orientation
   * - ``auto_contrast``
     - ``true``
     - Automatically adjust contrast
   * - ``default_gamma``
     - ``1.0``
     - Default gamma correction value

Processing Settings
===================

[Fitting]
---------

.. list-table::
   :widths: 30 20 50
   :header-rows: 1

   * - Option
     - Default
     - Description
   * - ``default_method``
     - ``mesh``
     - Default fitting method
   * - ``mesh_alpha``
     - ``1.0``
     - Alpha parameter for Alpha Shape
   * - ``mesh_radii``
     - ``5.0,3.5,1.0``
     - Ball radii for Ball Pivoting algorithm
   * - ``mesh_voxel_size``
     - ``10.0``
     - Voxel size for Poisson reconstruction
   * - ``mesh_depth``
     - ``9``
     - Octree depth for Poisson reconstruction

[Clustering]
------------

.. list-table::
   :widths: 30 20 50
   :header-rows: 1

   * - Option
     - Default
     - Description
   * - ``default_method``
     - ``connected``
     - Default clustering method
   * - ``dbscan_distance``
     - ``40.0``
     - DBSCAN epsilon parameter
   * - ``dbscan_min_points``
     - ``5``
     - DBSCAN minimum points parameter
   * - ``kmeans_k``
     - ``2``
     - Default number of K-means clusters

Example Configuration
=====================

Basic configuration example:

.. code-block:: ini

   [General]
   autosave = true
   autosave_interval = 300
   recent_files_count = 15

   [Performance]
   max_threads = 8
   cache_size = 4096

   [Display]
   background_color = #000000
   point_size = 10
   axes_visible = true

   [Colors]
   default_color = #ffffff
   highlight_color = #ff0000

   [Volume]
   default_colormap = viridis

   [Fitting]
   default_method = ellipsoid

Editing Configuration
=====================

GUI Configuration
-----------------

Most settings can be changed through the GUI:

1. Select **Edit > Preferences** from the menu
2. Navigate to the appropriate tab
3. Modify settings
4. Click **Apply** or **OK**

#Screenshot: Preferences dialog

Manual Editing
--------------

Configuration files are plain text and can be edited with any text editor:

1. Locate the configuration file
2. Open it with a text editor
3. Make changes following the INI format
4. Save the file
5. Restart Mosaic to apply changes

See Also
========
- :doc:`troubleshooting` for configuration-related issues
