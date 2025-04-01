=================
Specialized Views
=================

This section covers tools for visualizing volume data and time-series trajectories.

Volumes
=======

To active the viewer and load a volume file

1. Select **View > Volume Viewer** from the menu
2. The Volume Viewer panel appears at the bottom of the screen
3. In the Volume Viewer panel, click **Open**
4. Navigate to your volume file (.mrc, .map, .em)
5. Select the file and click **Open**

Click the **+** button to add another slice viewer. You can load multiple volumes by using the **Open** method of the newly added slice viewer.

Display Controls
----------------

- **Slice slider**: Browse through volume slices
- **Orientation selector**: Switch between X, Y, Z views
- **Min/Max contrast sliders**: Set display range
- **Gamma slider**: Adjust contrast curve
- **Color palette**: Change visualization (gray, viridis, magma, etc.)
- **Projection modes**: 
  - **Off**: Current slice only
  - **Project +/-**: Show structures in slice direction


Trajectories
============

Trajectories are sequence of structures representing the same object at different times points. In mosaic, we use them to assess HMFF simulation results. To open a trajectory:

1. Go to the **Intelligence** tab
2. Click **Trajectory** in the HMFF Operations section
3. Configure scale and offset settings
4. Select the directory with trajectory files (.tsi, .vtu, or mesh series)

Files should follow a numerical sequence (e.g., ``basename_001.tsi``, ``basename_002.tsi``, ...), as produced by FreeDTS.


.. note::

  Duplicating a trajectory object will not create a new trajectory but rather a Geometry object representing the current time point.


Using the Trajectory Player
---------------------------

1. Select **View > Trajectory Player** from the menu
2. Control options:
   - **Play/Pause**: Start/stop animation
   - **Previous/Next Frame**: Step through frames
   - **First/Last**: Jump to beginning/end
   - **Timeline**: Navigate to specific frames

Mosaic can display multiple trajectories simultaneously with independent controls.

To create a moview of the trajectory:

1. Set up the desired camera angle
2. Select **File > Export Animation** or press ``Ctrl+E``
3. Select **Trajectory** as Animation Type
4. Choose format, frame range, and rate
