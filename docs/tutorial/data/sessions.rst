==================
Session Management
==================

Mosaic allows you to save and restore complete workspaces with all data and settings.

A session includes:

- All data (clusters and models)
- Object visibility status
- Visual properties (colors, sizes, opacity)
- Object names and metadata

Sessions don't include the state of the camera and external files such as the state of the volume viewer.

Saving Sessions
===============

1. Select **File > Save Session** or press ``Ctrl+S``
2. Choose a location and filename (.pickle extension)
3. Click **Save**

#Screenshot: Save Session dialog

Use descriptive filenames like:
``project_stage_date.pickle``

Example: ``ribosomes_segmentation_20250401.pickle``

Loading Sessions
================

1. Select **File > Load Session** or press ``Ctrl+L``
2. Navigate to your session file
3. Click **Open**

This replaces your current workspace. Unsaved changes will be lost.

Recent Sessions
---------------

For quick access:
- Select **File > Recent Files**
- Choose a session from the list

Sharing Sessions
================

Note the mosaic version used when sharing sessions.
