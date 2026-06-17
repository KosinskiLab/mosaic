"""
A ``SculptTarget`` owns the float64 working copies of a mesh's vertex and face
arrays plus the lazy adjacency used by Smooth. A ``SculptSession`` wraps the
target with stroke state.

Two undo record shapes:
  - ``PositionRecord``: a stroke (Grab/Smooth) only displaces existing vertices.
  - ``SnapshotRecord``: a topology-changing op (Patch) replaces both arrays.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from dataclasses import dataclass
from typing import NamedTuple, Optional, Tuple, Union

import igl
import numpy as np

from .tools import build_adjacency, compute_boundary_mask


__all__ = [
    "PositionRecord",
    "SnapshotRecord",
    "SculptTarget",
    "SculptSession",
    "TOOLS",
    "TOOL_BY_HOTKEY",
    "TOOL_BY_ID",
    "ToolSpec",
    "UndoRecord",
]


@dataclass
class PositionRecord:
    """Stroke that displaced existing vertices. Stores both endpoints."""

    indices: np.ndarray
    before_positions: np.ndarray
    after_positions: np.ndarray


@dataclass
class SnapshotRecord:
    """Topology-changing op (Patch). Stores both endpoints of vs/fs."""

    before_vs: np.ndarray
    before_fs: np.ndarray
    after_vs: np.ndarray
    after_fs: np.ndarray


UndoRecord = Union[PositionRecord, SnapshotRecord]


class ToolSpec(NamedTuple):
    """Identity + presentation of a sculpt tool. Single source of truth."""

    id: str
    hotkey: str
    label: str
    color: Tuple[float, float, float]


TOOLS: Tuple[ToolSpec, ...] = (
    ToolSpec("view", "1", "1  View", (0.75, 0.78, 0.82)),
    ToolSpec("grab", "2", "2  Grab", (1.0, 0.71, 0.28)),
    ToolSpec("smooth", "3", "3  Smooth", (0.49, 0.83, 0.99)),
    ToolSpec("patch", "4", "4  Patch", (0.72, 0.58, 0.96)),
)

TOOL_BY_ID: dict[str, ToolSpec] = {t.id: t for t in TOOLS}
TOOL_BY_HOTKEY: dict[str, str] = {t.hotkey: t.id for t in TOOLS}


def _opt_copy(arr, dtype) -> Optional[np.ndarray]:
    return None if arr is None else np.asarray(arr, dtype=dtype).copy()


class SculptTarget:
    """Working buffers for one mesh under sculpt."""

    __slots__ = ("vs", "fs", "_adjacency", "_normals", "_boundary_mask")

    def __init__(self, vs: np.ndarray, fs: np.ndarray) -> None:
        self.vs = np.ascontiguousarray(vs, dtype=np.float64)
        self.fs = np.ascontiguousarray(fs, dtype=np.int64)
        self._adjacency = None
        self._normals: Optional[np.ndarray] = None
        self._boundary_mask: Optional[np.ndarray] = None

    @property
    def n(self) -> int:
        return int(self.vs.shape[0])

    @property
    def adjacency(self):
        if self._adjacency is None:
            self._adjacency = build_adjacency(self.fs, self.n)
        return self._adjacency

    @property
    def normals(self) -> np.ndarray:
        if self._normals is None or self._normals.shape != self.vs.shape:
            if len(self.fs) == 0:
                self._normals = np.zeros_like(self.vs)
            else:
                self._normals = np.asarray(
                    igl.per_vertex_normals(self.vs, self.fs), dtype=np.float64
                )
        return self._normals

    @property
    def boundary_mask(self) -> np.ndarray:
        if self._boundary_mask is None or self._boundary_mask.shape[0] != self.n:
            self._boundary_mask = compute_boundary_mask(self.fs, self.n)
        return self._boundary_mask

    def invalidate_normals(self) -> None:
        self._normals = None

    def replace_topology(self, new_vs: np.ndarray, new_fs: np.ndarray) -> None:
        """Swap in new vs and fs after Patch. Invalidates derived data."""
        self.vs = np.ascontiguousarray(new_vs, dtype=np.float64)
        self.fs = np.ascontiguousarray(new_fs, dtype=np.int64)
        self._adjacency = None
        self._normals = None
        self._boundary_mask = None


class SculptSession:
    """Stroke lifecycle for one ``SculptTarget``."""

    def __init__(self, target: SculptTarget) -> None:
        self.target = target
        self.tool: str = "view"
        self.in_stroke: bool = False
        self._stroke_snapshot: Optional[np.ndarray] = None
        self.anchor_world: Optional[np.ndarray] = None
        self.locked_indices: Optional[np.ndarray] = None
        self.locked_weights: Optional[np.ndarray] = None
        self.rest_positions: Optional[np.ndarray] = None
        self._painted_boundary: set = set()

    def set_tool(self, tool: str) -> None:
        if self.in_stroke:
            self.cancel_stroke()
        self.tool = tool

    def begin_stroke(
        self,
        anchor_world: Optional[np.ndarray] = None,
        locked_indices: Optional[np.ndarray] = None,
        locked_weights: Optional[np.ndarray] = None,
    ) -> None:
        self.in_stroke = True
        self._stroke_snapshot = self.target.vs.copy()
        self.anchor_world = _opt_copy(anchor_world, np.float64)
        self.locked_indices = _opt_copy(locked_indices, np.int64)
        self.locked_weights = _opt_copy(locked_weights, np.float64)
        self.rest_positions = (
            None
            if self.locked_indices is None
            else self.target.vs[self.locked_indices].copy()
        )
        self._painted_boundary = set()

    def accumulate_patch(self, indices_on_boundary: np.ndarray) -> None:
        """Add brushed boundary-vertex ids to the patch stroke accumulator."""
        if indices_on_boundary.size == 0:
            return None
        self._painted_boundary.update(int(v) for v in indices_on_boundary.tolist())
        return None

    def painted_boundary_indices(self) -> np.ndarray:
        """Vertex ids the Patch brush has crossed that lie on an open boundary."""
        if not self._painted_boundary:
            return np.empty(0, dtype=np.int64)
        return np.fromiter(self._painted_boundary, dtype=np.int64)

    def cancel_stroke(self) -> None:
        if not self.in_stroke:
            return None
        if self._stroke_snapshot is not None:
            self.target.vs = self._stroke_snapshot
        self._reset_stroke_fields()
        return None

    def commit_stroke(self) -> Optional[PositionRecord]:
        """Compute the stroke diff, finish the stroke, return the record."""
        if not self.in_stroke or self._stroke_snapshot is None:
            self._reset_stroke_fields()
            return None
        before = self._stroke_snapshot
        after = self.target.vs
        if before.shape != after.shape:
            self._reset_stroke_fields()
            raise RuntimeError(
                "strokes must not change topology; use apply_topology_change for Patch"
            )
        diff = np.linalg.norm(after - before, axis=1)
        changed = np.where(diff > 1e-9)[0].astype(np.int64)
        record: Optional[PositionRecord] = None
        if changed.size > 0:
            record = PositionRecord(
                indices=changed,
                before_positions=before[changed].copy(),
                after_positions=after[changed].copy(),
            )
        self.target.invalidate_normals()
        self._reset_stroke_fields()
        return record

    def apply_topology_change(
        self, new_vs: np.ndarray, new_fs: np.ndarray
    ) -> SnapshotRecord:
        """Capture before+after snapshots and swap in the new topology."""
        if self.in_stroke:
            self.cancel_stroke()
        record = SnapshotRecord(
            before_vs=self.target.vs.copy(),
            before_fs=self.target.fs.copy(),
            after_vs=np.ascontiguousarray(new_vs, dtype=np.float64).copy(),
            after_fs=np.ascontiguousarray(new_fs, dtype=np.int64).copy(),
        )
        self.target.replace_topology(new_vs, new_fs)
        return record

    def grab_state(
        self,
    ) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
        """Return ``(indices, weights, rest, anchor)`` for Grab, or None.

        The four Grab fields are populated by ``begin_stroke`` together and
        cleared together; one check is enough.
        """
        if self.locked_indices is None:
            return None
        return (
            self.locked_indices,
            self.locked_weights,
            self.rest_positions,
            self.anchor_world,
        )

    def _reset_stroke_fields(self) -> None:
        self.in_stroke = False
        self._stroke_snapshot = None
        self.anchor_world = None
        self.locked_indices = None
        self.locked_weights = None
        self.rest_positions = None
        self._painted_boundary = set()
