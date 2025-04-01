=================
Influenza A Virus
=================

IAV (Influenza A Virus) Workflow
============================

This tutorial guides you through analyzing Influenza A Virus (IAV) virus-like particles (VLPs) using Mosaic, from initial segmentation to creating coarse-grained molecular models.

Overview
--------

The workflow consists of these major steps:

1. Data acquisition
2. Initial segmentation with MemBrain-seg
3. Mesh generation and refinement
4. HMFF simulation
5. Constrained template matching of viral proteins
6. Backmapping to coarse-grained models

1. Data Acquisition
------------------

First, download the IAV virus-like particle (VLP) tomogram:

.. code-block:: bash

   # Download example IAV VLP tomogram (to be replaced with actual download command)
   wget https://example.org/iav_vlp_tomogram.mrc

2. Initial Segmentation
----------------------

Segment the membranes using MemBrain-seg:

1. Launch Mosaic and navigate to the **Intelligence** tab.
2. Click on the **Membrane** button in the **Segmentation Operations** section.
3. Select the IAV tomogram file.
4. Configure the MemBrain-seg parameters:

   - Model: Select appropriate model
   - Window Size: 160
   - Test-Time Augmentation: Enabled

The segmentation will be loaded into Mosaic automatically when complete.

3. Mesh Generation and Refinement
--------------------------------

3.1. Clean the Segmentation
^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. In the **Segmentation** tab, select the segmented cluster.
2. Click on **Thin** and choose "outer" to extract the outer cloud.
3. Remove any erroneous segments using the **Remove** function.

3.2. Generate Initial Mesh
^^^^^^^^^^^^^^^^^^^^^^^^^

1. Switch to the **Parametrization** tab.
2. Select the cleaned point cloud.
3. Click on **Mesh** and choose "Alpha Shape" with the following parameters:

   - Alpha: 1.0
   - Elastic Weight: 1.0
   - Curvature Weight: 10.0

3.3. Refine the Mesh
^^^^^^^^^^^^^^^^^^^

1. Sample from the mesh for a volumetric estimate:

   - Select the mesh.
   - Click on **Sample** and set:

     - Sampling Method: Distance
     - Sampling: 110

   - Click "Apply".

2. Manually examine and remove any undesirable samples.

3. Create a new mesh from the cleaned samples:

   - Select the cleaned samples.
   - Click on **Mesh** again, using Alpha Shape with:

     - Alpha: 1.0
     - Elastic Weight: 0.1
     - Pressure Weight: 0.1

4. Remesh to target edge length:

   - Select the new mesh.
   - Click on **Remesh**.
   - Set the target edge length to 110Å.

5. Equilibrate the mesh:

   - Select the remeshed model.
   - Click on **Equilibrate** in the **HMFF Operations** section.
   - Use default parameters:

     - Average Edge Length: 110
     - Steps: 5000
     - Kappa_b: 300
     - Other parameters at default values

4. HMFF Simulation
-----------------

1. Prepare the tomogram:

   - From the **View** menu, open **Volume Viewer**.
   - Load the IAV tomogram.
   - Apply bandpass filtering:

     - Low cutoff: 50Å
     - High cutoff: 900Å

2. Configure HMFF:

   - Select the equilibrated mesh.
   - Click on **Setup** in the **HMFF Operations** section.
   - Configure parameters:

     - Mesh: Select your equilibrated mesh
     - Volume: Select your filtered tomogram
     - Invert Contrast: Enabled
     - HMFF weight (ξ): 5.0
     - Rigidity (κ): 30.0
     - Steps: 50000
     - Threads: Set based on your system

   - Set volume coupling:

     - Kappa_v: 1000
     - Volume fraction: 1.1

3. Run the HMFF simulation:

   - A simulation folder will be created.
   - Run the simulation using:

   .. code-block:: bash

      cd /path/to/hmff_simulation_folder
      FreeDTS

4. Import the refined mesh:

   - After simulation completion, import the final .tsi or .vtu file.
   - In Mosaic, choose **Open** and select the final configuration.

5. Constrained Template Matching
-------------------------------

5.1. Generate Seed Points
^^^^^^^^^^^^^^^^^^^^^^^^

1. Create seed points from the HMFF-refined mesh:

   - Select the refined mesh.
   - Switch to the **Parametrization** tab.
   - Click on **Sample** with:

     - Sampling Method: Distance
     - Sampling: 40
     - Offset: 100

5.2. Prepare Templates
^^^^^^^^^^^^^^^^^^^^^

Prepare HA and NA protein templates:

1. Generate AlphaFold models:

   .. code-block:: bash

      # Example for HA from A/Hong-Kong/1/1968 H3N2 (UniProt: P11134)
      # Example for NA from A/California/04/2009 H1N1 (UniProt: C3W5S3)
      # Run AlphaFold with 6 refinement cycles

2. Convert structures to template maps with PyTME:

   .. code-block:: python

      # Python code using PyTME
      import pytme

      # For HA template
      ha_template = pytme.Template.from_pdb("ha_model.pdb")
      ha_template.align_to_z_axis()
      ha_template.to_density(voxel_size=6.8)
      ha_template.apply_lowpass_filter(resolution=27.2)
      ha_template.create_mask(shape="cylinder", height=251.6, radius=68.0, sigma=2.0)
      ha_template.save("ha_template.mrc")
      ha_template.mask.save("ha_mask.mrc")

      # Similar for NA template

5.3. Run Template Matching
^^^^^^^^^^^^^^^^^^^^^^^^^

Using PyTME for constrained template matching:

.. code-block:: python

   import pytme

   # Initialize template matcher
   matcher = pytme.TemplateMatcher(
       "ha_template.mrc",
       "tomogram.mrc",
       mask="ha_mask.mrc",
       score="flc"
   )

   # Configure constraints
   matcher.set_seed_points(
       "seed_points.tsv",  # Points exported from Mosaic
       max_angle=15,
       max_distance=(7, 7, 7)
   )

   # Run matching
   peaks_ha = matcher.match(
       angular_sampling=7,
       min_peak_distance=10,
       score_threshold=0.135,
       min_distance_to_mesh=100.0,
       max_distance_to_mesh=150.0
   )

   # Similarly for NA with score_threshold=0.12

5.4. Filter and Refine Results
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. Keep the top 97% of NA picks by score.
2. Remove HA picks that are within 7 voxels of NA picks to avoid clashes.
3. Visualize and verify the distribution in Mosaic.

6. Backmapping to Coarse-Grained Models
--------------------------------------

1. Remesh the HMFF-refined structure:

   - Select the mesh.
   - Click on **Remesh** and set the target edge length to 40Å.

2. Map proteins to vertices:

   - In Mosaic, use the **Backmapping** tool from the **HMFF Operations** section.
   - Map each picked protein to the nearest vertex.

3. Run TS2CG to generate a coarse-grained model:

   .. code-block:: bash

      # Use PLM utility to create a bilayer
      ts2cg.py PLM -f mesh.obj -o bilayer_mesh.obj -w 3.8

      # Use PCG utility to populate with lipids
      ts2cg.py PCG -f bilayer_mesh.obj -o cg_system.gro -a 0.64 -l POPC

      # Insert proteins with appropriate offsets
      ts2cg.py PAI -f cg_system.gro -p HA.pdb NA.pdb -o final_system.gro -z 12

4. The final model can be used for molecular dynamics simulations with GROMACS or visualization with VMD/ChimeraX.

Conclusion
----------

You have now completed the entire workflow for analyzing IAV virus-like particles, from tomogram segmentation to creating a detailed molecular model. This model can be used for further structural analysis or as starting configurations for molecular simulations.

References
----------

- MemBrain-seg: Lamm et al. (2024). bioRxiv, doi.org/10.1101/2024.01.05.574336
- FreeDTS: [Citation for FreeDTS]
- PyTME: [Citation for PyTME]
- TS2CG: [Citation for TS2CG]
- AlphaFold 2: Jumper et al. (2021). Nature, 596(7873), 583-589.
- AlphaFold Multimer: Evans et al. (2021). bioRxiv, doi.org/10.1101/2021.10.04.463034