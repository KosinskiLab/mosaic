# Release Notes v1.2.1

Version 1.2.1 introduces an interactive shell for scriptable control, along with mesh processing improvements and dependency cleanup.

## Features

- **Interactive Shell:** A REPL-based command interface (`mosaic-shell`) with auto-complete for scripting geometry operations, file I/O, and session management.
- **Batch Rename Dialog:** Rename multiple geometries at once.
- **Improved Texture Resolution:** Higher quality tomogram-on-mesh projections.

## Improvements

- Removed `pymeshlab` dependency; mesh repair now uses `libigl` exclusively.
- Migrated to `libigl==2.6.1`.
- Replaced MarchingCubes with FlyingEdges and windowed sinc smoothing.
- Unified pipeline executor into a single REPL-based module.
- Centralized method annotations in the operations registry.

## Bug Fixes

- Fixed trajectory animation updates during live view.
- Minor bug fixes in export dialog and property analysis.

## Installation

```bash
pip install -U mosaic-gui==1.2.1
```

---

# Release Notes v1.2.0

Version 1.2.0 introduces segmentation geometries, medial meshes, and interactive animation waypoints, alongside improvements to property analysis and rendering.

## Features

- **Segmentation Geometry:** A new geometry type for rendering dense segmentations more efficiently.
- **Tomogram Visualization on Meshes:** Visualize tomogram data projected onto mesh surfaces.
- **Membrane Thickness Computation:** Calculate membrane thickness as a geometry property.
- **Projection Angle Calculation:** Compute projection angles for geometry data.
- **Medial Meshes**
- **Interactive Animation Waypoints**

## Improvements

- Added filtering to the Property Analysis dialog.
- Added throttling to various interactive widgets for smoother performance.
- Made automatic property updates on render changes opt-in.
- LUT updates are now applied on filter changes.
- Show queued tasks in the task manager.
- Added mesh export support in pipeline configurations.
- Dock widgets share available screen space using scroll areas, avoiding overdrawing.
- Improved error handling in template matching scripts.

## Bug Fixes

- Fixed rendering inconsistencies with volume geometries.
- Fixed minor coloring bugs.
- Fixed normal vector rendering for geometries without normals.
- Fixed visual issue with pipeline cards.
- Fixed minor bugs in dialogs.

## Installation

```bash
pip install -U mosaic-gui==1.2.0
```

---

# Release Notes v1.1.0

Version 1.1.0 introduces pipelines, a major new feature for batch processing and automation, alongside several improvements to mesh processing and user interface.

## Features

- **Scriptable Pipeline System:** A complete pipelining module that enables batch processing workflows through both GUI and CLI (`mosaic-pipeline`). Includes a pipeline builder with composition safeguards and a dedicated tutorial in the documentation.
- **Composable Animations:** Animations can now be composed and scripted for creating complex visualization sequences.simplifying meshes.
- **Task Monitor** Better feedback during parallel operations with progress and stdout/stderr queue handling.
- **Searchable Object Browser** Quickly subset large object collections.

## Improvements

- Updated cache in Property Analysis operations to improve performance.
- Consolidated and updated widgets with refreshed styling.
- Allow for selecting multiple groups in object browser.
- Generalized remove and merge methods for geometry operations.
- FlyingEdges mesh algorithm now automatically closes edges.

## Bug Fixes

- Fixed coloring issue for Volume Geometries.
- Fixed display issues in the progress dialog.
- Fixed signal disconnects for dock widgets.

## Installation

```bash
pip install -U mosaic-gui==1.1.0
```
