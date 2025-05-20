============
Intelligence
============

The *Intelligence* tab provides advanced features for specialized tasks.

.. grid:: 2 3 3 4
    :gutter: 1

    .. grid-item-card:: Sphere
        :text-align: center
        :link: #sphere

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
2. Click **Equilibrate**
3. Configure parameters:
   - Average Edge Length: Target mesh resolution
   - Bounds: Min/max edge length
   - Energy coefficients: Control mesh behavior
4. Select output directory
5. An equilibration process prepares the mesh for simulation

Setup
-----

Configures HMFF simulation:

1. Click **Setup**
2. Select equilibrated mesh
3. Configure:
   - Volume data (MRC file)
   - Filtering options
   - Simulation parameters (steps, coefficients)
4. Select output directory
5. Files are prepared for HMFF simulation

Trajectory
----------

Imports simulation results:

1. Click **Trajectory**
2. Select directory with trajectory files
3. Configure scaling and offset
4. Trajectory is loaded into the Trajectory Player

Backmapping
-----------

Maps coarse-grained models to detailed structures:

1. Click **Backmapping**
2. Select surface fit (mesh)
3. Set edge length parameter
4. Add cluster mappings (protein structures)
5. The system is prepared for multi-scale modeling

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

Membrane
^^^^^^^^

Automatically segments membranes in tomograms:

1. Click **Membrane**
2. Select model path (neural network)
3. Configure:
   - Window Size: Processing block size
   - Sampling Rates: Input/output resolution
   - Clustering: Connected components option
4. Select tomogram file
5. Membrane structures are automatically segmented