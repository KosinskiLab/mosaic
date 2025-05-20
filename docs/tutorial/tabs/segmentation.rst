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

            <i class="mdi mdi-merge" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Remove
        :text-align: center
        :link: #remove

        .. raw:: html

            <i class="mdi mdi-delete" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Select
        :text-align: center
        :link: #select-by-size

        .. raw:: html

            <i class="mdi mdi-chart-histogram" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Transform
        :text-align: center
        :link: #transform

        .. raw:: html

            <i class="mdi mdi-rotate-right" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Crop
        :text-align: center
        :link: #crop

        .. raw:: html

            <i class="mdi mdi-map-marker-distance" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Cluster
        :text-align: center
        :link: #cluster

        .. raw:: html

            <i class="mdi mdi-sitemap" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Outlier
        :text-align: center
        :link: #outlier_removal

        .. raw:: html

            <i class="mdi mdi-filter" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Trim
        :text-align: center
        :link: #trim

        .. raw:: html

            <i class="mdi mdi-scissors-cutting" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Thin
        :text-align: center
        :link: #thin

        .. raw:: html

            <i class="mdi mdi-dots-horizontal" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Downsample
        :text-align: center
        :link: #downsample

        .. raw:: html

            <i class="mdi mdi-focus-field-horizontal" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Distances
        :text-align: center
        :link: #distances

        .. raw:: html

            <i class="mdi mdi-graphql" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Properties
        :text-align: center
        :link: #properties

        .. raw:: html

            <i class="mdi mdi-poll" style="font-size: 1.5rem;"></i>

.. _merge:

Merge
-----

Combines multiple clusters into a single object:

1. Select multiple clusters in the Object Browser
2. Click **Merge** in the ribbon or press ``M``

.. _remove:

Remove
------

Deletes selected clusters:

1. Select one or more clusters
2. Click **Remove** or press ``Delete``

.. _select_by_size:

Select by Size
--------------

Filters clusters by point count:

1. Click **Select** in the ribbon
2. Adjust the slider to set a minimum size threshold
3. Clusters below the threshold are automatically selected

.. _transform:

Transform
---------

Applies rotation and translation to clusters:

1. Select a cluster
2. Click **Transform**
3. Use the transformation widget to move or rotate the cluster

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
3. Choose method: Connected Components, DBSCAN, or K-Means
4. Configure method-specific options
5. Click **OK**

.. _outlier_removal:

Outlier Removal
---------------

Removes noise points:

1. Select a cluster to clean
2. Click **Outlier**
3. Choose method:
   - Statistical: Removes points based on average distance
   - Eigenvalue: Removes edge points
4. Set threshold and neighbors parameters
5. Click **OK**

.. _trim:

Trim
----

Removes points outside specified axis boundaries:

1. Select a cluster
2. Click **Trim**
3. Two cutting planes appear in the viewer
4. Position the planes or use X/Y/Z keys to align them
5. Points between planes are preserved

.. figure:: ../../_static/tutorial/trim_planes.png
    :width: 80%
    :align: center

    Trim planes in action

.. _thin:

Thin
----

Reduces point density while preserving structure:

1. Select a cluster
2. Click **Thin**
3. Choose method:
   - Outer: Keep surface points
   - Core: Keep central points
   - Inner: Keep interior points

.. _downsample:

Downsample
----------

Reduces the number of points while maintaining overall structure:

1. Select a cluster
2. Click **Downsample**
3. Configure sampling parameters:
   - Method: Random, Voxel Grid, or FPS
   - Factor: Reduction percentage
4. Click **OK**

.. _distances:

Distances
---------

Analyzes distances between clusters:

1. Click **Distances**
2. Select source and target objects
3. View distance distribution and statistics
4. Export data for external analysis

.. _statistics:

Properties
----------

Calculates geometric properties:

1. Click **Properties**
2. View point counts, bounds, centers, and densities
3. Export statistics as TSV file
