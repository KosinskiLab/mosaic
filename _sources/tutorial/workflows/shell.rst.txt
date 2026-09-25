===================
Scripting Interface
===================

.. versionadded:: 1.2.1

The Mosaic Shell provides headless access to most GUI operations and allows composing them into reproducible scripting workflows for remote servers and automated pipelines.

.. code-block:: bash

   mosaic-shell


Getting Started
---------------

The shell presents an interactive prompt with tab-completion for commands and geometry references. Use ``--log <path>`` to record all commands to a file that can be replayed later as a script.

The built-in help system reflects the same parameter definitions used by the GUI

.. code-block:: text

   mosaic> help                        # list all commands
   mosaic> help fit                    # show methods for an operation
   mosaic> help fit ball_pivoting      # show method-specific parameters


Loading Data
------------

Load individual files or use glob patterns to import entire directories. Supported formats include MRC, EM, STAR, PLY, OBJ, STL, and others documented in the :doc:`format reference <../../tutorial/reference/formats>`.

.. code-block:: text

   mosaic> open segmentation.mrc
   mosaic> open *.mrc
   mosaic> open segmentations/**/*.mrc

Import parameters can be specified inline

.. code-block:: text

   mosaic> open segmentation.mrc sampling_rate=14.08 offset=0,0,0


Inspecting Data
---------------

``list`` renders a formatted table of all loaded geometries showing index, point count, type, group, and name. Filter by any column using glob patterns or substring matching

.. code-block:: text

   mosaic> list
   mosaic> list Name=tomo_001*
   mosaic> list Type=mesh

Use ``info`` for detailed per-geometry metadata

.. code-block:: text

   mosaic> info #0


Targeting Geometries
--------------------

Most commands accept targets that specify which geometries to operate on

.. list-table::
   :widths: 20 80
   :header-rows: 0

   * - ``#0``, ``#3``
     - Individual geometries by index
   * - ``#0-5``
     - A contiguous range of geometries
   * - ``@last``
     - Results of the most recent operation
   * - ``*``
     - All geometries in the session

When no target is given, commands default to all geometries. New geometries created by an operation are appended to the session and become visible via ``list``.


Transient Results
-----------------

By default, every operation persists its output to the session. For intermediate steps where only the final result matters, use ``persist=false`` to keep results available via ``@last`` without cluttering the session

.. code-block:: text

   mosaic> fit #1-3 method=flying_edges persist=false
   mosaic> smooth @last method=taubin iterations=10

Here the raw mesh from ``fit`` is consumed by ``smooth`` and never stored.

.. tip::

   Transient results are the shell equivalent of the pipeline's **Save Output** toggle. Use them liberally in multi-step workflows.


Command Substitution
--------------------

Use ``$(...)`` to embed the output of one command inside another. Combined with ``list ... format=ids``, this lets you operate on filtered subsets without knowing their indices

.. code-block:: text

   mosaic> fit $(list Name=0* format=ids) method=ball_pivoting
   mosaic> save $(list Type=mesh format=ids) meshes format=ply


Organizing Results
------------------

**Renaming** uses ``s/pattern/replacement/[flags]`` syntax. Flags: ``i`` for case-insensitive, ``g`` for global (all occurrences)

.. code-block:: text

   mosaic> rename * s/seg/membrane/
   mosaic> rename #0-3 s/^/processed_/
   mosaic> rename * s/_/-/g

Direct renaming is also supported

.. code-block:: text

   mosaic> rename #0 Plasma_Membrane

**Grouping** organizes geometries into named collections

.. code-block:: text

   mosaic> group #0-2 Inner_Membranes
   mosaic> ungroup #0

**Removing** geometries by index

.. code-block:: text

   mosaic> remove #0-2


Analysis
--------

The ``measure`` command computes geometric properties. Type ``help measure`` for a full list.

Scalar results (point count, mesh area) are displayed as a value table. Per-vertex results (distance, curvature) show summary statistics including Min, Max, Mean, Std, and Median.

**Surface properties**

.. code-block:: text

   mosaic> measure mesh_curvature #1 curvature=gaussian
   mosaic> measure mesh_area #1

**Properties between geometries**

.. code-block:: text

   mosaic> measure distance #0 queries=#1
   mosaic> measure thickness #0 queries=#1

**Export to CSV**

.. code-block:: text

   mosaic> measure mesh_curvature #0 output=curvature.csv

**Storing per-vertex results** attaches values as vertex properties on each geometry. Stored properties can be retrieved with ``measure vertex_property`` or used as input to ``filter``

.. code-block:: text

   mosaic> measure distance #0 queries=#1 store=true
   mosaic> measure vertex_property #0 name=distance


Filtering
---------

The ``filter`` command removes geometries or individual points based on a property value range. It automatically detects whether the property yields per-vertex arrays (point-level filtering) or scalars (population-level filtering).

**Population-level** filtering removes entire geometries whose scalar property falls outside the bounds

.. code-block:: text

   mosaic> filter * property=n_points lower=100
   mosaic> filter #0-5 property=mesh_area upper=5000

**Point-level** filtering subsets individual vertices in-place. Requires a stored vertex property (via ``store=true``) or a property that naturally returns per-vertex values

.. code-block:: text

   mosaic> measure distance #0 queries=#1 store=true
   mosaic> filter #0 property=distance lower=10 upper=50

Geometries where all points are filtered out are removed from the session. Additional keyword arguments are passed through to the property computation

.. code-block:: text

   mosaic> filter #0 property=distance lower=5 queries=#1


Sessions
--------

Save and restore the full workspace state including all geometries, groups, and metadata

.. code-block:: text

   mosaic> save_session checkpoint.pickle
   mosaic> load_session checkpoint.pickle


Putting It Together
-------------------

The following script takes a dense membrane segmentation through mesh generation, refinement, and analysis. Each step builds on ``@last``, and ``persist=false`` keeps intermediates out of the final session

.. code-block:: text

   # Load segmentation
   open segmentation.mrc sampling_rate=14.08

   # Separate into distinct compartments
   cluster @last method=connected_components

   # Remove small fragments
   filter @last property=n_points lower=2000

   # Generate and smooth mesh
   fit @last method=flying_edges persist=false
   remesh @last method=decimation reduction=10 persist=false
   remesh @last method=subdivision persist=false

   # Analyze
   measure mesh_area @last
   measure mesh_curvature @last output=curvature.csv

   # Export
   save @last refined_mesh format=ply
   save_session meshing.pickle


Scripts
-------

Save commands to a file and replay them. Lines starting with ``#`` (not followed by a digit) are treated as comments

.. code-block:: bash

   mosaic-shell workflow.sh

For single commands without entering the interactive shell

.. code-block:: bash

   mosaic-shell -c "open data.mrc"

.. tip::

   Use ``--log session.log`` during interactive exploration to capture a reproducible record of your session. The log file can be replayed directly.
