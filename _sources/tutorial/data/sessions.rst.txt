==================
Session Management
==================

Mosaic allows you to save and restore complete workspaces with all data and settings.

A session includes:

- All data (clusters and models)
- Object visibility status
- Visual properties (colors, sizes, opacity) and attached models
- Object names and metadata

Sessions don't include the state of the camera and external files such as the state of the volume viewer.

Saving Sessions
---------------

1. Select **File > Save Session** (⌘ + S for macOS / Ctrl + S)
2. Choose a location and filename (.pickle extension)
3. Click **Save**

Note the mosaic version used when sharing sessions.

Loading Sessions
----------------

1. Select **File > Load Session** (⌘ + N for macOS / Ctrl + N)
2. Navigate to your session file
3. Click **Open**

This replaces your current workspace. Unsaved changes will be lost.


Programmatic Access for Developers
----------------------------------

Mosaic uses the :py:func:`open_session <mosaic.formats.reader.open_session>` function to import sessions from pickle files. Generally, session files are not intended to be used directly, but can be be useful for developers building custom workflows.

An example is shown below:

.. code-block:: python

	from mosaic.formats import open_session

	session = open_session("path/to/session.pickle")
	session
	# {
	# 	"shape"   : Shape of the bounding box (optional)
	# 	"_data"   : DataContainer storing cluster data
	# 	"_models" : DataContainer storing model data,
	# }

The session file contains two :py:class:`DataContainer <mosaic.container.DataContainer>` objects that contain cluster and model data respectively. DataContainer instances are a collection of atomic :py:class:`Geometry <mosaic.geometry.Geometry>` objects, each of which corresponds to a distinct object in the *Object Browser*. See :py:func:`MosaicData.load_session <mosaic.data.MosaicData.load_session>` for how they can be used.


Next Steps
----------

Continue to :doc:`special` to learn how to visualize volume data and mesh trajectories.
