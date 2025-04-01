=====================
Mycoplasma Pneumoniae
=====================

Mycoplasma pneumoniae Workflow
============================

This tutorial guides you through analyzing *Mycoplasma pneumoniae* using Mosaic, from initial segmentation to creating coarse-grained molecular models with ribosome localization.

Overview
--------

The workflow consists of these major steps:

1. Data acquisition
2. Initial segmentation with MemBrain-seg
3. Mesh generation and refinement
4. HMFF simulation
5. Constrained template matching of Nap proteins
6. Ribosome localization
7. Backmapping to coarse-grained models

1. Data Acquisition
------------------

First, download the *M. pneumoniae* tomogram:

.. code-block:: bash

   # Download example M. pneumoniae tomogram
   wget https://example.org/mycoplasma_pneumoniae_tomogram.mrc

2. Initial Segmentation
----------------------

Segment the bacterial membrane using MemBrain-seg:

1. Launch Mosaic and navigate to the **Intelligence** tab.
2. Click on the **Membrane** button in the **Segmentation Operations** section.
3. Select the *M. pneumoniae* tomogram file.
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
     - Sampling: 100

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
   - Set the target edge length to 170Å.

5. Equilibrate the mesh:

   - Select the remeshed model.
   - Click on **Equilibrate** in the **HMFF Operations** section.
   - Use default parameters:

     - Average Edge Length: 170
     - Steps: 5000
     - Kappa_b: 300
     - Other parameters at default values

4. HMFF Simulation
-----------------

1. Prepare the tomogram:

   - From the **View** menu, open **Volume Viewer**.
   - Load the *M. pneumoniae* tomogram.
   - Apply bandpass filtering:

     - Low cutoff: 140Å
     - High cutoff: 900Å

   - Normalize each z-slice by dividing by its maximum density value:
     - In the Volume Settings, select "Normalize axis" and choose "z"

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
     - Temperature (T): 1.5

3. Run the HMFF simulation:

   - A simulation folder will be created.
   - Run the simulation using:

   .. code-block:: bash

      cd /path/to/hmff_simulation_folder
      FreeDTS

4. Import the refined mesh:

   - After simulation completion, import the final .tsi or .vtu file.
   - In Mosaic, choose **Open** and select the final configuration.

5. Constrained Template Matching of Nap Proteins
-----------------------------------------------

5.1. Generate Seed Points
^^^^^^^^^^^^^^^^^^^^^^^^

1. Create seed points from the HMFF-refined mesh:

   - Select the refined mesh.
   - Switch to the **Parametrization** tab.
   - Click on **Sample** with:

     - Sampling Method: Distance
     - Sampling: 80
     - Offset: 80

5.2. Prepare Template
^^^^^^^^^^^^^^^^^^^^

Prepare the Nap protein template:

1. Download the Nap protein structure:

   .. code-block:: bash

      # Download PDB:8pbz for Nap particle template
      wget https://files.rcsb.org/download/8pbz.pdb

2. Convert structure to template map with PyTME:

   .. code-block:: python

      # Python code using PyTME
      import pytme

      # For Nap template
      nap_template = pytme.Template.from_pdb("8pbz.pdb")
      nap_template.align_to_z_axis()
      nap_template.to_density(voxel_size=13.604)
      nap_template.apply_lowpass_filter(resolution=13.604)

      # Create a spherical mask centered on extracellular head group
      nap_template.create_mask(
          shape="sphere",
          radius=81.6,
          center=[0, 0, 0],  # Adjust center to match extracellular head group
          sigma=1.0
      )

      nap_template.save("nap_template.mrc")
      nap_template.mask.save("nap_mask.mrc")

5.3. Run Template Matching
^^^^^^^^^^^^^^^^^^^^^^^^^

Using PyTME for constrained template matching:

.. code-block:: python

   import pytme

   # Initialize template matcher
   matcher = pytme.TemplateMatcher(
       "nap_template.mrc",
       "mycoplasma_tomogram.mrc",  # Use tomogram with voxel size 6.80Å
       mask="nap_mask.mrc",
       score="flc"
   )

   # Configure constraints
   matcher.set_seed_points(
       "seed_points.tsv",  # Points exported from Mosaic
       max_angle=15,
       max_distance=(10, 10, 20)  # Ellipse with radii (10,10,20) voxels
   )

   # Run matching
   peaks_nap = matcher.match(
       angular_sampling=7,
       min_peak_distance=20,
       score_threshold=0.09,
       min_distance_to_mesh=70.0,
       max_distance_to_mesh=120.0
   )

5.4. Filter and Verify Results
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. Visualize the template matching results in Mosaic by importing the peaks file.
2. Verify the distribution of Nap proteins on the cell surface.

6. Ribosome Localization
-----------------------

6.1. Prepare Ribosome Template
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. Download ribosome template:

   .. code-block:: bash

      # Download EMD:17132 for ribosome template
      wget https://ftp.ebi.ac.uk/pub/databases/emdb/structures/EMD-17132/map/emd_17132.map.gz
      gunzip emd_17132.map.gz

2. Prepare the template:

   .. code-block:: python

      import pytme

      # Load and prepare ribosome template
      ribosome_template = pytme.Template.from_map("emd_17132.map")
      ribosome_template.apply_lowpass_filter(resolution=27.2)
      ribosome_template.resample(voxel_size=13.60)

      # Create a spherical mask
      ribosome_template.create_mask(shape="sphere", radius=142.8)

      ribosome_template.save("ribosome_template.mrc")
      ribosome_template.mask.save("ribosome_mask.mrc")

6.2. Run Template Matching
^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   import pytme

   # Initialize template matcher
   matcher = pytme.TemplateMatcher(
       "ribosome_template.mrc",
       "mycoplasma_tomogram.mrc",  # Tomogram with voxel size 13.60Å
       mask="ribosome_mask.mrc",
       score="flc"
   )

   # Run matching
   peaks_ribosome = matcher.find_peaks(
       peak_finder="scipy",
       min_peak_distance=15,
       score_threshold=0.21
   )

6.3. Manual Refinement
^^^^^^^^^^^^^^^^^^^^^

1. Import the ribosome picks into Mosaic.
2. Manually refine the picks to remove false positives and adjust positions.

7. Backmapping to Coarse-Grained Models
--------------------------------------

1. Remesh the HMFF-refined structure:

   - Select the mesh.
   - Click on **Remesh** and set the target edge length to 120Å.

2. Map proteins to vertices:

   - In Mosaic, use the **Backmapping** tool from the **HMFF Operations** section.
   - Map the Nap proteins to the nearest vertices.

3. Run TS2CG to generate a coarse-grained model:

   .. code-block:: bash

      # Use PLM utility to create a bilayer
      ts2cg.py PLM -f mesh.obj -o bilayer_mesh.obj -w 3.8

      # Use PCG utility to populate with lipids
      ts2cg.py PCG -f bilayer_mesh.obj -o cg_system.gro -a 0.64 -l POPC

      # Insert Nap proteins with appropriate offsets
      ts2cg.py PAI -f cg_system.gro -p nap.pdb -o final_system.gro -z 6.5

4. The final model can be used for molecular dynamics simulations with GROMACS or visualization with VMD/ChimeraX.

Conclusion
----------

You have now completed the entire workflow for analyzing *Mycoplasma pneumoniae*, from tomogram segmentation to creating a detailed molecular model with localized Nap proteins and ribosomes. This model can be used for further structural analysis or as starting configurations for molecular simulations.

References
----------

- MemBrain-seg: Lamm et al. (2024). bioRxiv, doi.org/10.1101/2024.01.05.574336
- Nap protein structure: Sprankel et al. (2023). [Reference details]
- Ribosome template: Xue et al. (2025). [Reference details]
- FreeDTS: [Citation for FreeDTS]
- PyTME: [Citation for PyTME]
- TS2CG: [Citation for TS2CG]