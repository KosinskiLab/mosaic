============
Intelligence
============

The *Intelligence* tab provides advanced features for specialized tasks.

.. grid:: 2 3 3 4
    :gutter: 1

    .. grid-item-card:: Equilibrate
        :text-align: center
        :link: #equilibrate

        .. raw:: html

            <i class="mdi mdi-molecule" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Setup
        :text-align: center
        :link: #setup

        .. raw:: html

            <i class="mdi mdi-export" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Trajectory
        :text-align: center
        :link: #trajectory

        .. raw:: html

            <i class="mdi mdi-chart-line-variant" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Backmapping
        :text-align: center
        :link: #backmapping

        .. raw:: html

            <i class="mdi mdi-set-merge" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Setup
        :text-align: center
        :link: #template-matching

        .. raw:: html

            <i class="mdi mdi-magnify" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Add
        :text-align: center
        :link: #add

        .. raw:: html

            <i class="mdi mdi-plus" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Membrane
        :text-align: center
        :link: #membrane

        .. raw:: html

            <i class="mdi mdi-border-all-variant" style="font-size: 1.5rem;"></i>

Equilibrate
-----------

Prepares meshes for simulation:

1. Select a mesh model
2. Configure parameters:

   - **Average Edge Length**: Target edge length for mesh uniformity
   - **Steps**: Number of equilibration iterations
   - **Energy coefficients**: Control mesh equilibration
3. **Choose directory**: Click **Equilibrate** and select an output directory for simulation files
4. Click **OK** to start the equilibration

**Output Files:**

- `mesh_base`: Original input mesh
- `mesh_remeshed`: Mesh with target edge length
- `mesh_equilibrated`: Fully equilibrated mesh ready for simulation
- `mesh.txt`: Configuration file with mesh scale and offest parameters

.. note::

    The Trimem library for mesh equilibration (see :ref:`installation instructions <installation-dts>`).

Setup
-----

Configures Helfrich Monte Carlo Flexible Fitting (HMFF) simulation:

1. Click **Setup** and choose a directory containing equilibrated meshes.
2. Select from available equilibrated mesh files
3. Configure parameters:

   :Input Data:
      - **Volume**: Select volume file with densities (MRC format)
      - **Invert Contrast**: Flip density values if needed

   :HMFF Parameters:
      - **HMFF Weight (ξ)**: Coupling strength to experimental data
      - **Rigidity (κ)**: Membrane bending rigidity
      - **Steps**: Number of simulation steps
      - **Threads**: Parallel processing threads

   :Filtering Options:
      - **Lowpass Cutoff**: High-frequency noise removal
      - **Highpass Cutoff**: Low-frequency artifact removal

4. Select output directory
5. Files are prepared for HMFF simulation

Simulation can be executed via the generated `run.sh` script.

.. note::

    Requires FreeDTS for simulation (see :ref:`installation instructions <installation-dts>`).


Trajectory
----------

Imports and visualizes DTS simulation results:

1. Click the arrow next to **Trajectory**
2. Configure import settings:

   - **Scale**: Coordinate scaling factor (1/scale applied to points)
   - **Offset**: Coordinate offset (single value or x,y,z triplet)
3. Select directory with a DTS trajectory from FreeDTS
4. Trajectory is loaded into the Trajectory Player

**Supported Formats:**

- **TSI**: FreeDTS topology files (.tsi, .q)
- **VTU**: VTK unstructured grid files (.vtu)

.. tip::

    Use **View > Trajectory Player** to navigate through time points.

Backmapping
-----------

Creates coarse-grained molecular models of membrane surfaces, optionally including protein positions and orientations.

1. Click **Backmapping** and choose location for generated coarse-grained files
2. elect a mesh model as the membrane surface
3. Configure parameters:

   :Mesh Settings:
      - **Target Edge Length**: Spatial resolution for coarse-grained model

   :Protein Inclusions:
      - **Add mappings**: Associate point cloud clusters with protein types
      - **Include Normals**: Preserve orientation information
      - **Flip Normals**: Reverse normal direction if needed

4. The system is prepared for multi-scale modeling

**Output Files:**

- `mesh.tsi`: DTS-compatible mesh with protein inclusions
- `martinize.sh`: Script for protein coarse-graining
- `plm.sh`: Bilayer generation script
- `pcg.sh`: Lipid population script

.. note::

    Requires TS2CG for backmapping (see :ref:`installation instructions <installation-backmapping>`).

Template Matching
-----------------

Setup
^^^^^

Configures template matching for protein identification:

1. Click **Setup** in the Template Matching section
2. Configure data paths:

   - Input tomogram
   - Template structures
   - Output directory
3. Set matching parameters:

   - Angular sampling
   - Score function
   - Uncertainty values
4. Configure computational resources
5. Run template matching to identify protein positions

Segmentation Operations
-----------------------

Add
---
Creates new empty clusters for manual point addition:

1. Click **Add** in the Segmentation section
2. A new empty cluster appears in the Object Browser
3. Use drawing mode (``A`` key) to manually add points
4. Or use for testing with random point generation

.. note::

    This function is included for testing and might be removed in a future release.

Membrane Segmentation
---------------------

Automatically segments cellular membranes in tomograms using MemBrain-seg:

1. Click **Membrane**
2. Select model path (neural network weights - typically a .cpt file)
3. Configure parameters:

   :Model Settings:
      - **Model Path**: Location of MemBrain-seg checkpoint file
      - **Window Size**: Processing block size (160 recommended)
      - **Augmentation**: Enable test-time augmentation for robustness

   :Post-processing:
      - **Clustering**: Group connected components
      - **Sampling Rates**: Input/output resolution scaling
4. Select tomogram file and run segmentation

The output will be automatically loaded into the GUI. A copy of the segmentation is created in $HOME/mosaic/segmentations/membrain.

.. note::

    A GPU is required to perform membrane segmentation in reasonable time.

