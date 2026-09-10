============
Segmentation
============

The *Segmentation* tab provides tools for refinement, clustering and analysis.

.. grid:: 2 3 3 4
    :gutter: 1

    .. grid-item-card:: Merge
        :text-align: center
        :link: #merge

        .. raw:: html

            <i class="ph ph-git-merge" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Remove
        :text-align: center
        :link: #remove

        .. raw:: html

            <i class="ph ph-trash" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Select
        :text-align: center
        :link: #select-by-size

        .. raw:: html

            <i class="ph ph-chart-bar" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Transform
        :text-align: center
        :link: #transform

        .. raw:: html

            <i class="ph ph-arrows-out-cardinal" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Crop
        :text-align: center
        :link: #crop

        .. raw:: html

            <i class="ph ph-crop" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Cluster
        :text-align: center
        :link: #cluster

        .. raw:: html

            <i class="ph ph-arrows-out-line-horizontal" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Outlier
        :text-align: center
        :link: #outlier_removal

        .. raw:: html

            <i class="ph ph-funnel" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Normals
        :text-align: center
        :link: #normals

        .. raw:: html

            <i class="ph ph-arrows-out" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Trim
        :text-align: center
        :link: #trim

        .. raw:: html

            <i class="ph ph-scissors" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Skeletonize
        :text-align: center
        :link: #skeletonize

        .. raw:: html

            <i class="ph ph-line-segments" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Downsample
        :text-align: center
        :link: #downsample

        .. raw:: html

            <i class="ph ph-arrows-in" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Properties
        :text-align: center
        :link: #properties

        .. raw:: html

            <i class="ph ph-chart-bar-horizontal" style="font-size: 1.5rem;"></i>

.. _merge:

Merge
-----

Combines multiple clusters or creates new clusters from point selections:

**For complete clusters:**

1. Select multiple clusters in the Object Browser
2. Click **Merge** in the ribbon or press ``m`` after clicking the viewport.
3. Selected clusters are combined into a single new cluster

**For point selections:**

1. Use area selection (``R`` key) to select points from one or more clusters
2. Click **Merge** or press ``m`` after clicking the viewport.
3. A new cluster is created containing only the selected points
4. Original clusters remain but without the selected points


.. _remove:

Remove
------

Deletes selected clusters or removes points from clusters:

**For complete clusters:**

1. Select one or more clusters in the Object Browser
2. Click **Remove** or press ``Delete`` after clicking the viewport.
3. Selected clusters are completely deleted

**For point selections:**

1. Use area selection (``R`` key) to select points within clusters
2. Click **Remove** or press ``Delete`` after clicking the viewport.
3. Only the selected points are removed from their parent clusters
4. Empty clusters are automatically deleted

.. _select_by_size:

Select by Size
--------------

Filters clusters by point count:

1. Click **Select** in the ribbon
2. Adjust the slider to set a minimum size threshold
3. Clusters below the threshold are automatically selected
4. Use in combination with **Remove** to clean up small clusters

.. _transform:

Transform
---------

Applies rotation and translation to clusters:

1. Select a cluster in the Object Browser
2. Click **Transform**
3. A 3D transformation widget appears around the cluster
4. Use the transformation widget to move or rotate the cluster
5. Press **Transform** again to exit transformation mode

.. _crop:

Crop
----

Trims points based on distance to other structures:

1. Click **Crop**
2. Select source structures to crop
3. Select target structures to measure distance from
4. Set the distance threshold
5. Choose to keep points within or beyond the threshold

.. _cluster:

Cluster
-------

Groups points into separate clusters:

1. Select a cluster with multiple distinct structures
2. Click **Cluster**
3. Choose clustering method:

   - **Connected Components**: Groups connected components (default). Particularly useful for postprocessing volume segmentations
   - **Envelope**: Retrieve boundaries of dense membrane segmentation
   - **Leiden**: Partition connected segmentations into distinct objects
   - **DBSCAN**: Density-based clustering with distance and minimum points parameters
   - **K-Means**: Divides into a specified number of clusters
   - **Birch**: Hierarchical clustering

4. Configure method-specific parameters:

   :Leiden:
      - **Resolution**: Clustering resolution. Lower values yield larger cluster.

   :DBSCAN:
      - **Distance**: Maximum distance between points in the same cluster
      - **Min Points**: Minimum points required to form a cluster

   :K-Means:
      - **K**: Number of target clusters

   :Birch:
      - **Clusters**: Number of target clusters
      - **Threshold**: Radius threshold for merging subclusters (lower values create more clusters)
      - **Branching Factor**: Maximum subclusters per node (affects memory usage and clustering speed)

5. Click **OK** to apply clustering


.. _outlier_removal:

Outlier Removal
---------------

Removes noise points using statistical methods:

1. Select a cluster to clean
2. Click **Outlier**
3. Choose removal method:

   - **Statistical**: Removes points based on distance to neighbors
   - **Eigenvalue**: Removes edge points using covariance analysis

4. Configure method-specific parameters:

   - **Neighbors**: Number of neighbors to consider for statistics
   - **Threshold**: Sensitivity of outlier detection (lower = more aggressive)


.. _normals:

Normals
-------

Modulate normals of a point cloud object

1. Select a cluster
2. Click **Normals**
3. Choose method:

   - **Compute**: Recompute normals by orienting point cloud normal vector field.
   - **Flip**: Flip normals

4. Configure method-specific parameters:

   :Compute:
      - **Neighbors**: Number of neighboring points to consider

.. _trim:

Trim
----

Select points outside specified axis-aligned boundaries:

1. Select a cluster
2. Click **Trim**
3. Two cutting planes appear in the 3D viewer
4. Position the planes by dragging or use keyboard shortcuts:

   - ``X``: Align planes to X-axis
   - ``C``: Align planes to Y-axis
   - ``Z``: Align planes to Z-axis

5. Points between the planes are preserved
6. Press **Trim** again to exit trim mode

.. _thin:

Skeletonize
-----------

Skeletonize point cloud:

1. Select a cluster
2. Click **Skeletonize**
3. Choose method:

   - **Core**: Classical internal skeleton.
   - **Boundary**: Exo-like skeleton of boundaries.
   - **Outer**: Outer exo-like skeleton.
   - **Outer_Hull**: Legacy method to compute the outer hull of a point cloud. Used to be listed under **Thin** pre v1.0.16.

4. Click **OK** to apply thinning

.. _downsample:

Downsample
----------

Reduces the number of points while maintaining overall structure:

1. Select a cluster
2. Click **Downsample**
3. Choose downsampling method:

   - **Radius**: Remove points within a specified distance of each other
   - **Number**: Randomly subsample to a target number of points

4. Configure parameters:

   - **Radius**: Minimum distance between retained points
   - **Size**: Target number of points for random subsampling

5. Click **OK** to apply downsampling

.. _distances:


Properties
----------

Advanced analysis and visualization dialog with three modes: **Visualize**, **Distribution**, and **Statistics**.

1. Select objects in the Object Browser
2. Click **Properties** in the ribbon
3. Use **Compute** to calculate properties, then switch between tabs

**Property Categories:**

- **Distance**: To camera, clusters, or models
- **Surface**: Curvature, edge length, surface area, volume
- **Geometric**: Dimensions, point counts, identity
- **Projection**: Projected curvature, geodesic distance

**Visualization Options:**

- **Color Maps**: Common colormaps (viridis, plasma, etc.)
- **Normalization**: Per-object or global scaling
- **Quantiles**: Statistical binning for outlier handling
- **Interactive**: Real-time color mapping in 3D viewport

**Visualize Tab:** Compute geometric properties and display as interactive color maps in the 3D viewport.

**Distribution Tab:** Generate interactive export-ready histograms, density plots, and line charts with customizable styling.

**Statistics Tab:** View numerical summaries (min, max, mean, std dev) and export data as CSV/TSV files.

.. tip::

    All data can be exported using the **Export Data** button.
