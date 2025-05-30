===============
Parametrization
===============

The *Parametrization* tab provides tools for fitting and working with models.

.. grid:: 2 3 3 4
    :gutter: 1

    .. grid-item-card:: Sphere
        :text-align: center
        :link: #sphere

        .. raw:: html

            <i class="mdi mdi-circle" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Ellipse
        :text-align: center
        :link: #ellipsoid

        .. raw:: html

            <i class="mdi mdi-ellipse" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Cylinder
        :text-align: center
        :link: #cylinder

        .. raw:: html

            <i class="mdi mdi-hexagon" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: RBF
        :text-align: center
        :link: #rbf

        .. raw:: html

            <i class="mdi mdi-grid" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Mesh
        :text-align: center
        :link: #mesh

        .. raw:: html

            <i class="mdi mdi-triangle-outline" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Curve
        :text-align: center
        :link: #curve

        .. raw:: html

            <i class="mdi mdi-chart-bell-curve" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Sample
        :text-align: center
        :link: #sample

        .. raw:: html

            <i class="mdi mdi-chart-scatter-plot" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: To Cluster
        :text-align: center
        :link: #to-cluster

        .. raw:: html

            <i class="mdi mdi-plus" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Remove
        :text-align: center
        :link: #remove

        .. raw:: html

            <i class="mdi mdi-delete" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Merge
        :text-align: center
        :link: #merge-meshes

        .. raw:: html

            <i class="mdi mdi-merge" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Volume
        :text-align: center
        :link: #volume

        .. raw:: html

            <i class="mdi mdi-cube-outline" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Repair
        :text-align: center
        :link: #repair

        .. raw:: html

            <i class="mdi mdi-auto-fix" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Remesh
        :text-align: center
        :link: #remesh

        .. raw:: html

            <i class="mdi mdi-repeat" style="font-size: 1.5rem;"></i>

    .. grid-item-card:: Project
        :text-align: center
        :link: #project

        .. raw:: html

            <i class="mdi mdi-vector-curve" style="font-size: 1.5rem;"></i>


Parametric Fitting
==================
Fit basic geometric shapes to point clouds:

.. _sphere:

Sphere
------
Fits a sphere using least squares optimization:

1. Select a cluster with spherical shape
2. Click **Sphere** to fit the model
3. The fitted sphere appears in the Models section

.. _ellipsoid:

Ellipsoid
---------
Fits an ellipsoid using eigenvalue decomposition and least squares optimization:

1. Select a cluster with ellipsoidal shape
2. Click **Ellipsoid** to fit the model
3. The fitted ellipsoid appears in the Models section

.. _cylinder:

Cylinder
--------
Fits a cylinder using PCA and iterative refinement:

1. Select a cluster with cylindrical or tubular shape
2. Click **Cylinder** to fit the model
3. The fitted cylinder appears in the Models section

.. _rbf:

Non-Parametric Fitting
======================

.. _rbf:

RBF (Radial Basis Function)
---------------------------
Creates smooth, non-parametric surface models through radial basis function interpolation. Ideal for complex, non-parametric shapes that can be represented as height fields, i.e. an open membrane section.

1. Select a cluster with surface-like structure
2. Click **RBF**
3. Configure interpolation direction:

   - **xy**: Surface as function of x,y coordinates
   - **xz**: Surface as function of x,z coordinates
   - **yz**: Surface as function of y,z coordinates
4. Click **OK** to create the interpolated surface

.. _mesh:

Mesh
----
1. Select a cluster with sufficient point density
2. Click **Mesh**
3. Choose reconstruction method:

   - **Alpha Shape**: Convex hull with alpha parameter control
   - **Ball Pivoting**: Robust surface reconstruction for structured data
   - **Cluster Ball Pivoting**: Ball pivoting with automatic parameter determination
   - **Poisson**: Watertight surface reconstruction

4. Configure method-specific parameters:

   :Alpha Shape Parameters:
      - **Alpha**: Controls shape complexity (higher = coarser features)
      - **Scaling Factor**: Mesh resampling resolution
      - **Distance**: Threshold for inferred vs. measured vertices

   :Ball Pivoting Parameters:
      - **Radii**: Ball radii for reconstruction (comma-separated, e.g., "5,3.5,1.0")
      - **Downsample**: Thin input point cloud to core points
      - **Smoothing Steps**: Pre-smoothing iterations

   :Poisson Parameters:
      - **Depth**: Octree depth (higher = more detail)
      - **Samples**: Minimum points per octree node
      - **Pointweight**: Interpolation weight of input points

5. Set repair parameters:

   - **Elastic Weight**: Controls mesh elasticity (0 = strong anchoring)
   - **Curvature Weight**: Controls curvature propagation
   - **Volume Weight**: Controls internal mesh pressure
   - **Hole Size**: Maximum hole area for automatic filling

6. Click **OK** to generate the mesh

**Note**: Mesh quality depends on point cloud density and noise levels. For noisy data, increase smoothing steps. For sparse data, reduce the number of neighbors.

.. _curve:

Curve
-----
Fits spline curves of requested order to sequential control point data. Good for creating smooth curves from hand-drawn paths:

1. **Create control points** using drawing mode:

   - Press ``Shift+A`` to enter curve drawing mode
   - Click to place control points in sequence
   - Press ``Enter`` to complete the curve
   - *OR* select an existing cluster with linear structure

2. Click **Curve**
3. Configure spline parameters:
   - **Order**: Spline degree (1=linear, 3=cubic, 5=quintic)
4. Click **OK** to fit the curve


Sampling Operations
===================

.. _sample:

Sample
------
Creates point clouds from fitted models:

1. Select one or more models in the Object Browser
2. Click **Sample**
3. Configure sampling parameters:

   :Sampling Method:
      - **Points**: Generate specified number of points
      - **Distance**: Generate points with specified average spacing

   :Parameters:**
      - **Sampling**: Number of points or point spacing value
      - **Offset**: Normal-direction offset from surface (useful for particle picking)

4. Click **OK** to generate sample points

.. _to-cluster:

To Cluster
----------

Converts model vertices to point cloud format:

1. Select one or more models in the Object Browser
2. Click **To Cluster**
3. Model vertices are automatically added as new clusters

.. note::
    For most models, both vertices and computed normals are preserved in the conversion.

.. _remove:

Remove
------
Deletes selected models:

1. Select one or more models in the Object Browser
2. Click **Remove** or press ``Delete``
3. Selected models are permanently removed


Mesh Operations
===============

.. _volume:

Volume
------
Creates meshes from volumetric data using marching cubes:

1. Click **Volume**
2. Select a volume file (MRC, MAP, EM, HDF5)
3. Configure meshing parameters:

   :Algorithm Settings:
      - **Simplification Factor**: Reduce triangle count by this factor
      - **Workers**: Number of parallel processing threads
      - **Close Dataset Edges**: Create closed meshes at volume boundaries

   :Processing Method:
      - Uses sharded marching cubes algorithm for large volumes
      - Splits volume into manageable chunks for parallel processing
      - Merges submeshes and applies quadratic edge collapse simplification

4. Click **OK** to generate meshes

.. note::

    Optimized for large datasets with automatic memory management and parallel processing.

.. _repair:

Repair
------
Fixes mesh topology issues and fills holes using Leipa triangulation and fairing:

1. Select mesh models to repair
2. Click **Repair**
3. Configure repair parameters:

   :Optimization Weights:
      - **Elastic Weight**: Mesh smoothness (0=anchor to original, 1=free movement)
      - **Curvature Weight**: Preserve or modify curvature
      - **Volume Weight**: Internal pressure (positive=inflation, negative=shrinkage)
      - **Boundary Ring**: Optimize n-ring vertices around boundaries

   :Hole Filling:
      - **Hole Size**: Maximum hole area to fill (-1=fill all holes)

4. Click **OK** to repair meshes

.. _remesh:

Remesh
^^^^^^

Improves mesh quality and adjusts triangle density:

1. Select mesh models to remesh
2. Click **Remesh**
3. Choose remeshing method:

   :Edge Length:
      - **Edge Length**: Target average edge length
      - **Iterations**: Number of optimization passes
      - **Mesh Angle**: Preserve edges above this angle threshold

   :Vertex Clustering:
      - **Radius**: Clustering radius for vertex merging

   :Quadratic Decimation:
      - **Triangles**: Target triangle count

   :Subdivide:
      - **Iterations**: Number of subdivision passes
      - **Smooth**: Use smooth Loop subdivision vs. simple midpoint

4. Configure method-specific parameters
5. Click **OK** to remesh

**Use Cases:**

- **Edge Length**: Create uniform triangle sizes for simulation
- **Vertex Clustering**: Quick mesh simplification
- **Quadratic Decimation**: High-quality mesh reduction
- **Subdivide**: Increase resolution for detailed modeling

.. _project:

Project
-------
Projects point clouds onto mesh surfaces using ray casting:

1. Select exactly one mesh model (target surface)
2. Select one or more point cloud clusters (sources to project)
3. Click **Project**
4. Configure projection settings:

   :Projection Method:
      - **Cast Normals**: Use point normal vectors for ray casting
      - **Invert Normals**: Reverse normal direction

5. Click **OK** to perform projection

**Results:**

- Creates new point clouds with projected coordinates
- Generates updated mesh with projection points integrated
- Preserves original data while adding projected versions

.. _merge-meshes:

Merge
-----
Combines multiple meshes into a single object:

1. Select two or more mesh models in the Object Browser
2. Click **Merge**
3. Meshes are automatically combined into a single mesh
4. Original meshes are removed, replaced by the merged result


Next Steps
----------
Continue to the :doc:`intelligence` tab to learn about advanced features like HMFF and membrane segmentation.
