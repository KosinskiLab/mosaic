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
