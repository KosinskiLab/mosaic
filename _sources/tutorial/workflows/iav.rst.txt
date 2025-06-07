=================
Influenza A Virus
=================

This tutorial guides you through analyzing Influenza A Virus (IAV) virus-like particles (VLPs) using Mosaic, taking you from initial segmentation to creating coarse-grained Martini models.

.. figure:: ../../_static/tutorial/iav_workflow/mosaic_workflow.png
   :width: 100 %
   :align: center

   Coming up

Requirements
------------

First, install Mosaic according to the :doc:`installation instructions <../installation>`. For HMFF functionality, install the additional requirements listed in :ref:`DTS Simulations <installation-dts>`. If you plan to backmap DTS models to coarse-grained representations, install the tools listed in the :ref:`DTS Backmapping <installation-backmapping>` section.

.. note::

   Membrane segmentation, template-matching and the equilibration of coarse-grained model equilibration require a GPU to complete in reasonable time. You can download intermediate results of compute-intensive task and additional material from `ownCloud <https://oc.embl.de/index.php/s/fi7bJDRtAbVcOnt>`_.

We'll use publicly available cryo-ET data of an IAV VLP [1]_, which you can download from `EMDB-11075 <https://www.ebi.ac.uk/emdb/EMD-11075>`_ or via command line

.. code-block:: bash

   wget https://ftp.ebi.ac.uk/pub/databases/emdb/structures/EMD-11075/map/emd_11075.map.gz
   gunzip emd_11075.map.gz && mv emd_11075.map emd_11075.mrc

For membrane segmentation, download the MemBrain_seg_v10_alpha weights [2]_ from `Google Drive <https://drive.google.com/file/d/1tSQIz_UCsQZNfyHg0RxD-4meFgolszo8/view>`_.


Visual Demonstration
--------------------

The video below demonstrates the workflow from raw cryo-ET data to initial meshes, covering membrane segmentation, mesh generation, and refinement steps detailed in the following sections.

..  youtube:: -XyxZpJQoXA
   :width: 100%


Membrane Segmentation
---------------------

1. Launch Mosaic and navigate to the **Intelligence** tab.
2. Click on the arrow next to the **Membrane** button and configure:

   - Click the *Browse* button to select the downloaded model ckpt file.
   - Window Size: 160
   - Clustering: Enabled
   - Augmentation: Enabled
5. Click *Apply* and select the downloaded IAV VLP tomogram.

The status indicator will change from "Ready" to "Membrane Segmentation." The results will automatically load into Mosaic when complete.

.. note::

   Membrane segmentation requires a GPU. If unavailable, download the pre-computed segmentation `emd_11075_MemBrain_seg_v10_alpha.ckpt_segmented.mrc.gz <https://oc.embl.de/index.php/s/fi7bJDRtAbVcOnt>`_ and load it using File > Open.


Mesh Creation
-------------


Clean the Segmentation
^^^^^^^^^^^^^^^^^^^^^^

1. Switch to the **Segmentation** tab
2. Use the **Select** button to identify and **Remove** clusters corresponding to small artifacts
3. Eliminate incorrectly segmented voxels using manual selection (press **r** key) and deletion (press **del** key)
4. Select the central IAV VLP in the object browser and use the **Thin** button from the **Segmentation** tab with the *outer* option to extract the outer segmentation layer

.. raw:: html

   <div class="before-after-container" style="display: flex; gap: 10px;">
     <div style="flex: 1;">
       <img src="../../_static/tutorial/iav_workflow/segmentation_raw.png" style="width: 100%;">
      <p style="color: #707070">Before segmentation cleanup</p>
     </div>
     <div style="flex: 1;">
       <img src="../../_static/tutorial/iav_workflow/segmentation_clean.png" style="width: 100%;">
         <p style="color: #707070">After segmentation cleanup</p>
     </div>
   </div>


Generate Initial Mesh
^^^^^^^^^^^^^^^^^^^^^

1. Switch to the **Parametrization** tab.
2. Select the cleaned segmentation in the *Cluster* section of the *Object Browser*.
3. Click on the arrow next to the **Mesh** buton and configure:

   - Method: Ball Pivoting
   - Elastic Weight: 1.0
   - Curvature Weight: 10.0
   - Volume Weight: 0.0
   - Boundary Ring: 0
   - Neighbors: 15
   - Radii: 60.0
   - Hole Size: -1.0
   - Downsample: True
   - Smoothing Steps: 5
4. Click *Apply* to fit the mesh, creating a new object in the *Model* section.

.. figure:: ../../_static/tutorial/iav_workflow/initial_mesh_5550.png
   :width: 100 %
   :align: center

   Initial mesh


Refine the Mesh
^^^^^^^^^^^^^^^

Since one cap of the IAV VLP falls outside the tomogram, we'll extend it to mitigate boundary effects in subsequent simulations:

1. Sample points from the created mesh.

   - Select the mesh in the *Object Browser*.
   - Click on the arrow next to the **Sample** button and set:

     - Sampling Method: Points
     - Sampling: 30000

   - Click *Apply*.

2. Manually remove the cap that would fall outside the tomogram using the selection tool.

3. Create a new mesh from the cleaned samples.

   - Select the cleaned samples in the *Object Browser*.
   - Click the arrow next to **Mesh** again and configure:

     - Method: Ball Pivoting
     - Elastic Weight: 1.0
     - Curvature Weight: 10.0
     - Volume Weight: 0.005
     - Boundary Ring: 0
     - Neighbors: 15
     - Radii: 60.0
     - Hole Size: -1.0
     - Downsample: True
     - Smoothing Steps: 5
4. Click *Apply* to fit the mesh.

.. raw:: html

   <div class="before-after-container" style="display: flex; gap: 10px;">
     <div style="flex: 1;">
       <img src="../../_static/tutorial/iav_workflow/segmentation_sample_0600.png" style="width: 100%;">
      <p style="color: #707070">Cleaned mesh points</p>
     </div>
     <div style="flex: 1;">
       <img src="../../_static/tutorial/iav_workflow/mesh_pressurized_0600.png" style="width: 100%;">
         <p style="color: #707070">Pressurized mesh</p>
     </div>
   </div>


Equilibrate the Mesh
^^^^^^^^^^^^^^^^^^^^

Before DTS simulation, meshes require equilibration to ensure stability and physical validity:

1. Select the refined mesh model from the *Object Browser*
2. Navigate to the **Intelligence** tab and click **Equilibrate**
3. Configure:

   - Average Edge Length: 100
   - Steps: 5000
   - Other parameters at default values

Once complete, Mosaic will create three meshes in the target directory:

- mesh_base: the input mesh
- mesh_remeshed: input mesh with desired edge length
- mesh_equilibrated: the fully equilibrated mesh using Trimem [3]_

.. figure:: ../../_static/tutorial/iav_workflow/edge_lengths.png
   :scale: 40 %
   :align: right

   Comparison of edge lengths

To assess edge-length distribution, import the meshes into Mosaic and use the **Properties** button in the **Segmentation** tab. We typically choose the equilibrated mesh for DTS simulation due to its smoother surface and more predictable behavior.


.. note::

   Pre-computed equilibrated meshes are available from `ownCloud <https://oc.embl.de/index.php/s/fi7bJDRtAbVcOnt>`_.


HMFF Simulation
---------------

Navigate to the **Intelligence** tab and click **Setup** in the **DTS Simulation** section. Configure:

.. figure:: ../../_static/tutorial/iav_workflow/hmff_setup.png
   :scale: 40 %
   :align: right

   HMFF simulation setup dialog

- Mesh: Select mesh_equilibrated.q
- Volume: Select the downloaded EMD-11075.
- Invert Contrast: Enabled
- HMFF weight (ξ): 5.0
- Rigidity (κ): 25.0
- Steps: 150000
- Threads: 8 (or 1 for Mac unless FreeDTS is properly configured)
- Lowpass cutoff: 50Å
- Highpass cutoff: 900Å

This will create a filtered density map and setup files for DTS simulation [4]_ with HMFF. Open input.dts and set:

- AlexanderMove   = MetropolisAlgorithmOpenMP 0
- VolumeCoupling  = SecondOrder 0.6 1000 1.1

Run the simulation (takes less than five minutes with 8 threads):

.. code-block:: bash

      bash run.sh

.. note::

   Simulation outputs are available on `ownCloud <https://oc.embl.de/index.php/s/fi7bJDRtAbVcOnt>`_ in hmff/TrajTSI_Done.

To analyze the refined mesh in Mosaic:

1. Click the arrow next to the **Trajectory** button in the **Intelligence** tab
2. Configure the settings to match the input.dts file:

   - Scale: 0.012202743213335199
   - Offset: 21.0,6.0,16.0

Mosaic will load all trajectory time points. Use View > Trajectory player to navigate through them. To assess the results, open the density file in View > Volume Viewer and adjust contrast as needed. Compare the mesh at step 0 (left) and step 150,000 (right) to see how HMFF has refined the mesh to better match the viral membrane.

.. raw:: html

   <div class="before-after-container" style="display: flex; gap: 10px;">
     <div style="flex: 1;">
       <img src="../../_static/tutorial/iav_workflow/hmff_t0.png" style="width: 100%;">
      <p style="color: #707070">Initial mesh.</p>
     </div>
     <div style="flex: 1;">
       <img src="../../_static/tutorial/iav_workflow/hmff_t150.png" style="width: 100%;">
         <p style="color: #707070">HMFF-refined mesh.</p>
     </div>
   </div>


.. note::

   If you notice vertices frozen in place throughout the simulation, this indicates the simulation is unable to develop them. Try increasing Min_Max_Lenghts or choose a lower edge length for equilibration to increase mesh resolution.


Constrained Template Matching
-----------------------------

Generate Seed Points
^^^^^^^^^^^^^^^^^^^^

To create seed points from the HMFF-refined mesh:

1. Select your desired time-point in the trajectory
2. Right-click the trajectory object in the *Object Browser* and select **Duplicate**
3. Move to the **Parametrization** tab and configure **Sample**:

   - Sampling Method: Distance
   - Sampling: 40
   - Offset: 100

This generates seed points approximately 40Å apart with a 100Å offset from the surface, which should position them near the centers of HA and NA proteins. Both can be validated using the **Properties** button in the **Analysis** section of the **Segmentation** tab. The offset should roughly correspond to the center of the protein-of-interest, in our case Hemagglutinin (HA) and Neuraminidase (NA).

Export the cluster object as a STAR file by right-clicking on it.


Template Matching
^^^^^^^^^^^^^^^^^

The following outlines how to perform constrained template matching using PyTME [5]_.

1. **Launch the PyTME Template Matching Dialog**:

   - Navigate to the **Intelligence** tab
   - Click on **Setup** in the Template Matching directive.

2. **Prepare Data**:
   - In the "Data" tab, specify your working directory
   - Set paths to the EMD-11075 tomogram and the HA/NA structures

3. **Prepare Templates**:

   - Switch to the "Preprocess" tab to configure template preparation
   - Set Lowpass to 15
   - Set Align Template Axis to z
   - Set Flip Template to checked

4. **Configure Template Matching**:

   - In the "Matching" tab configure template matching parameters.
   - Set Angular Step to 7
   - Set Score Function to FLC
   - Set the path to the STAR file with seed points
   - Set Rotational Uncertainty to 15
   - Set Translational Uncertainty to (6,6,10) for HA and (6,6,12) for NA due to the longer stalk.
   - Set Tilt Range to -60, 60
   - Set Wedge Axes to 2, 0
   - Set Defocus to 30000
   - Set No Centering to checked

5. **Set Peak Calling Parameters**:

   - Switch to the "Peak Calling" tab
   - Set Peak Caller PeakCallerMaximumFilter
   - Set Number of Peaks 10000
   - Set Minimum Distance 7 for HA and 10 for NA

6. **Configure Compute Resources**:

   - In the "Compute" tab, allocate CPU cores and memory
   - Set backend cupy.

7. **Execute the Workflow**:

   - Click "OK" to generate the template matching scripts
   - Mosaic will create and organize all necessary files in your working directory
   - Run the generated scripts to perform template matching

.. note::

   Template matching results are available from `ownCloud <https://oc.embl.de/index.php/s/fi7bJDRtAbVcOnt>`_.


Refine Protein Picks
^^^^^^^^^^^^^^^^^^^^

The template matching process generates coordinate files for HA and NA that need filtering:

1. Keep the top 97% of NA picks by score.
2. Visualize and manually refine the picks in Mosaic using the selection tool (or the GUI provided with PyTME).
3. Remove HA picks that are within 7 voxels of NA picks to avoid clashes.

Example filtering scripts are available from `ownCloud <https://oc.embl.de/index.php/s/fi7bJDRtAbVcOnt>`_, namely pytme/filter.py and pytme/resolve_clash.py.


Coarse-Grained Martini Models
-----------------------------


Backmapping
^^^^^^^^^^^

We can now combined HMFF-refined membrane models with experimentally determined protein positions to create coarse-grained Martini model representations of IAV VLP

1. In the **Intelligence** tab, click **Backmapping** and select an output directory
2. Set target edge length to 20 (corresponds to 20Å in this case) and add both NA and HA inclusions
3. Navigate to the specified directory

.. tip::

   The output directory will also contain a file *mesh.tsi*, which can be used for equilibrium DTS simulations with protein inclusions.


Coarse Graining
^^^^^^^^^^^^^^^

Open the file *martinize.sh* and add paths to PDB files for *NA_STRUCTURE* and *HA_STRUCTURE*. Save the file and run

.. code-block:: bash

   bash martinize.sh

.. note::

   The principal axis of both proteins is required to align with the z-axis. This can be achieved with different tools. An example script using PyTME is available from `ownCloud <https://oc.embl.de/index.php/s/fi7bJDRtAbVcOnt>`_, namely pytme/templates/rot_structures.py.

Once the command above is completed, we can create a coarse-grained representation of the entire system using TS2CG [6]_

.. code-block:: bash

   # Use PLM utility to create a bilayer
   bash plm.sh

   # Use PCG utility to populate with lipids
   bash pcg.sh

This creates system.gro, which can be used for molecular dynamics simulation or visualization using e.g. Mosaic/VMD.


Equilibration
^^^^^^^^^^^^^

Gromacs [7]_ settings for Martini [8]_ model equilibration are available from `ownCloud <https://oc.embl.de/index.php/s/fi7bJDRtAbVcOnt>`_ in the ts2cg folder:

.. code-block:: bash

   bash equilibrate.sh

This performs energy minimization which can be run on a standard laptop. The final equilibration step should be run in an HPC environment (see eq/equilibrate.sbatch for an example).


Conclusion
----------

You've now completed the entire workflow for analyzing IAV virus-like particles—from tomogram segmentation to creating a detailed molecular model. This model can serve as a foundation for structural analysis or as a starting system for molecular simulations.

References
----------

.. [1] Peukes, J., Xiong, X., Erlendsson, S., Qu, K., Wan, W., Calder, L.J., Schraidt, O., Kummer, S., Freund, S.M.V., Kräusslich, H.G., Briggs, J.A.G. (2020). "The native structure of the assembled matrix protein 1 of influenza A virus". Nature, 587, 495-498. https://doi.org/10.1038/s41586-020-2696-8
.. [2] Lamm, L., Sieber, J., Chung, J.E. et al. (2024). "MemBrain-seg: Deep learning-based segmentation of cellular membranes in cryo-electron tomography". bioRxiv, doi.org/10.1101/2024.01.05.574336
.. [3] Siggel, M., Kehl, S., Reuter, K., Köfinger, J., Hummer, G. (2022). "TriMem: A parallelized hybrid Monte Carlo software for efficient simulations of lipid membranes". Journal of Chemical Physics, 157, 174801. https://doi.org/10.1063/5.0101118
.. [4] Pezeshkian, W., Ipsen, J.H. (2024). "Mesoscale simulation of biomembranes with FreeDTS". Nature Communications, 15, 548. https://doi.org/10.1038/s41467-024-44819-w
.. [5] Maurer, V.J., Siggel, M., Kosinski, J. (2024). "PyTME (Python Template Matching Engine): A fast, flexible, and multi-purpose template matching library for cryogenic electron microscopy data". SoftwareX, 25, 101636. https://doi.org/10.1016/j.softx.2023.101636
.. [6] Pezeshkian, W., König, M., Wassenaar, T.A., Marrink, S.J. (2020). "Backmapping triangulated surfaces to coarse-grained membrane models". Nature Communications, 11, 2296. https://doi.org/10.1038/s41467-020-16094-y
.. [7] Abraham, M.J., Murtola, T., Schulz, R., Páll, S., Smith, J.C., Hess, B., Lindahl, E. (2015). "GROMACS: High performance molecular simulations through multi-level parallelism from laptops to supercomputers". SoftwareX, 1-2, 19-25. https://doi.org/10.1016/j.softx.2015.06.001
.. [8] Souza, P.C.T., Alessandri, R., Barnoud, J., Thallmair, S., Faustino, I., Grünewald, F., Patmanidis, I., Abdizadeh, H., Bruininks, B.M.H., Wassenaar, T.A., Kroon, P.C., Melcr, J., Nieto, V., Corradi, V., Khan, H.M., Domański, J., Javanainen, M., Martinez-Seara, H., Reuter, N., Best, R.B., Vattulainen, I., Monticelli, L., Periole, X., Tieleman, D.P., de Vries, A.H., Marrink, S.J. (2021). "Martini 3: a general purpose force field for coarse-grained molecular dynamics". Nature Methods, 18, 382-388. https://doi.org/10.1038/s41592-021-01098-3