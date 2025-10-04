=================
HeLa Mitochondria
=================

Mitochondria Workflow
=====================

This tutorial guides you through analyzing mitochondria from cellular tomography data using Mosaic, from acquiring segmentations to HMFF refinement and potential downstream applications.

Overview
--------

The workflow consists of these major steps:

1. Data acquisition
2. Initial mesh generation from segmentations
3. Mesh cleaning and refinement
4. HMFF simulation
5. Analysis and downstream applications

1. Data Acquisition
-------------------

First, download the jrc-hela2 cellular segmentation dataset:

.. code-block:: bash

   # Download the jrc-hela2 dataset using the quilt data client
   pip install quilt3

   # Python script to download specific data
   python -c "import quilt3; quilt3.Package.browse('janelia-cosem-datasets/jrc_hela-2', registry='s3://janelia-cosem-datasets').fetch('jrc_hela-2/mitochondria/s0')"

This will download the mitochondria segmentation volume at full resolution (4nm, 4nm, 5.24nm).

2. Initial Mesh Generation
--------------------------

2.1. Convert Segmentation to Mesh
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Convert the volumetric segmentations to initial meshes using marching cubes:

.. code-block:: python

   import numpy as np
   import zmesh
   from skimage import io

   # Load the segmentation volume
   seg_volume = io.imread("jrc_hela-2/mitochondria/s0/volume.tif")

   # Split into manageable subvolumes
   subvolume_size = 448
   meshes = []

   # Process subvolumes with zmesh
   for x in range(0, seg_volume.shape[0], subvolume_size):
       for y in range(0, seg_volume.shape[1], subvolume_size):
           for z in range(0, seg_volume.shape[2], subvolume_size):
               # Extract subvolume
               x_end = min(x + subvolume_size, seg_volume.shape[0])
               y_end = min(y + subvolume_size, seg_volume.shape[1])
               z_end = min(z + subvolume_size, seg_volume.shape[2])

               subvol = seg_volume[x:x_end, y:y_end, z:z_end]

               # Skip empty subvolumes
               if not np.any(subvol):
                   continue

               # Generate mesh for subvolume
               submesh = zmesh.Mesh.from_numpy(subvol)

               # Simplify mesh with reduction factor
               submesh = submesh.simplify(reduction_factor=100, max_error=40)

               meshes.append(submesh)

   # Save the meshes for later use
   for i, mesh in enumerate(meshes):
       mesh.write(f"mitochondria_submesh_{i}.obj")

2.2. Merge and Further Simplify Meshes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. Load the individual submeshes into Mosaic:

   - Use **File > Open** to load each .obj file.

2. Merge the submeshes:

   - Select all loaded submeshes.
   - In the **Parametrization** tab, click **Merge**.

3. Simplify the merged mesh using Mosaic's mesh operations:

   - Select the merged mesh.
   - Click on **Remesh** with:

     - Method: Quadratic Decimation
     - Target Triangle Count: [Appropriate value, e.g., 50000]

   Or alternatively, use pyfqmr for more control:

   .. code-block:: python

      import pyfqmr
      import trimesh

      # Load merged mesh
      mesh = trimesh.load("merged_mitochondria.obj")

      # Setup mesh simplifier
      simplifier = pyfqmr.Simplify()
      simplifier.setMesh(mesh.vertices, mesh.faces)

      # Simplify with an aggressiveness of 5.5 and decimation factor of 2.0
      simplifier.simplify_mesh(target_count=len(mesh.faces)//2,
                               aggressiveness=5.5,
                               preserve_border=True)

      # Get simplified mesh
      v, f = simplifier.getMesh()

      # Save simplified mesh
      simplified_mesh = trimesh.Trimesh(vertices=v, faces=f)
      simplified_mesh.export("simplified_mitochondria.obj")

3. Mesh Cleaning and Refinement
-------------------------------

3.1. Import and Assess Mesh Quality
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. Import the simplified mesh into Mosaic:

   - Use **File > Open** to load the simplified mesh.

2. Assess mesh quality:

   - Inspect for disconnected components, holes, and non-manifold edges.
   - Use the **Analyze** tool in the **Mesh Operations** section to check metrics.

3.2. Clean and Repair the Mesh
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. Generate equidistant samples from the mesh:

   - Select the mesh.
   - Click on **Sample** with:

     - Sampling Method: Distance
     - Sampling: 20 (in nm, adjust based on your dataset)

2. Remove erroneous segments manually.

3. Close gaps by creating a new mesh from the cleaned samples:

   - Select all cleaned samples.
   - Click on **Mesh** using "Poisson" reconstruction:

     - Depth: 9-14 (adjust based on complexity)
     - Scale: 1.2
     - Pointweight: 0.1

4. Remesh to target edge length for simulation:

   - Select the new mesh.
   - Click on **Remesh**.
   - Set method to "Edge Length" with target edge length of 20nm.

4. HMFF Simulation
------------------

4.1. Prepare the Tomogram
^^^^^^^^^^^^^^^^^^^^^^^^^

1. Import the jrc-hela2 tomogram (at an appropriate binning level):

   - From the **View** menu, open **Volume Viewer**.
   - Load the tomogram with voxel size of 16nm × 16nm × 20.96nm.

2. No additional preprocessing is typically needed for this dataset.

4.2. Configure HMFF
^^^^^^^^^^^^^^^^^^^

1. Select the remeshed mitochondria model.

2. Click on **Setup** in the **HMFF Operations** section.

3. Configure parameters:

   - Mesh: Select your remeshed mitochondria mesh
   - Volume: Select your tomogram
   - Invert Contrast: Based on your dataset contrast
   - HMFF weight (ξ): 50.0
   - Rigidity (κ): 15.0
   - Steps: 50000
   - Threads: Set based on your system
   - Temperature (T): 1.5

4.3. Run the HMFF Simulation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. A simulation folder will be created by the setup step.

2. Run the simulation using:

   .. code-block:: bash

      cd /path/to/hmff_simulation_folder
      FreeDTS

3. Monitor the simulation progress and energy minimization.

4.4. Import the Refined Mesh
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. After simulation completion, import the final .tsi or .vtu file:

   - In Mosaic, choose **File > Open** and select the final configuration.

2. Visually inspect the refined mesh against the tomogram data.

5. Analysis and Downstream Applications
---------------------------------------

5.1. Quantitative Analysis
^^^^^^^^^^^^^^^^^^^^^^^^^^

1. Calculate mesh properties:

   - Select the refined mesh.
   - Use the **Analyze** tool to compute properties like surface area, volume, and curvature.

2. Export statistics for further analysis:

   - Save the generated statistics using the export function.

5.2. Visualization
^^^^^^^^^^^^^^^^^^

1. Create high-quality renderings:

   - Use **File > Save Screenshot** to capture the current view.
   - Adjust lighting and backgrounds for optimal visualization.

2. Create videos of the mesh:

   - Use **File > Export Animation** to create a video rotating around the mitochondria.

5.3. Further Modeling (Optional)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If desired, you can proceed with additional modeling steps similar to the IAV and Mycoplasma workflows:

1. Generate seed points for protein placement.

2. Map proteins of interest using constrained template matching.

3. Backmap to coarse-grained models for simulations:

   .. code-block:: bash

      # Use TS2CG for backmapping (if applicable)
      ts2cg.py PLM -f refined_mitochondria.obj -o bilayer_mesh.obj -w 4.0
      ts2cg.py PCG -f bilayer_mesh.obj -o cg_system.gro -a 0.64 -l POPC:POPE:CARD -r 2:2:1

Conclusion
----------

You have now completed the workflow for analyzing mitochondria from cellular tomography data. This workflow demonstrates how to process complex cellular organelles from segmentations to refined meshes using Mosaic and HMFF. The resulting models can be used for structural analysis, visualization, and potentially as starting configurations for molecular simulations.

References
----------

- JRC Hela-2 dataset: Heinrich et al. (2021) [Citation information]
- zmesh: [Citation for zmesh]
- pyfqmr: [Citation for pyfqmr]
- Igneous: [Citation for Igneous]
- FreeDTS: [Citation for FreeDTS]
- PyTME: [Citation for PyTME]
- TS2CG: [Citation for TS2CG]