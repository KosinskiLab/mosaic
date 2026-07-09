"""SculptController behavioural tests.

The controller is exercised without a real renderer: events go through
``handle_event`` and ``handle_hotkey``; tool dispatch is verified by checking
the session and target state directly.
"""

from unittest.mock import MagicMock

import numpy as np
import pytest
import vtk
from vtkmodules.util import numpy_support

from mosaic.sculpt.controller import Brush, EventKind, MeshHit, SculptController
from mosaic.sculpt.session import TOOL_BY_ID
from mosaic.undo import STACK


@pytest.fixture(autouse=True)
def _reset_stack():
    STACK.clear()
    yield
    STACK.clear()


class _FakeTriMesh:
    def __init__(self, fs: np.ndarray) -> None:
        self.triangles = np.asarray(fs, dtype=np.int64)


class _FakeGeometry:
    def __init__(self, vs: np.ndarray, fs: np.ndarray, uuid: str = "g") -> None:
        self.uuid = uuid
        polydata = vtk.vtkPolyData()
        vtk_pts = vtk.vtkPoints()
        vtk_pts.SetData(numpy_support.numpy_to_vtk(vs.astype(np.float32), deep=True))
        polydata.SetPoints(vtk_pts)
        cells = vtk.vtkCellArray()
        for tri in fs:
            cells.InsertNextCell(3, tri.tolist())
        polydata.SetPolys(cells)
        self._data = polydata
        self.model = _FakeTriMesh(fs)
        self.color_calls = []
        self.set_color_calls = 0

    @property
    def points(self):
        return numpy_support.vtk_to_numpy(self._data.GetPoints().GetData())

    def color_points(self, point_ids, color):
        self.color_calls.append((np.asarray(point_ids, dtype=np.int32), tuple(color)))

    def set_color(self, color=None):
        self.set_color_calls += 1


def _attach(controller, mesh):
    vs, fs, *_ = mesh
    geom = _FakeGeometry(vs, fs)
    controller.attach_geometry(geom)
    return geom


def test_attach_geometry_initialises_session(perturbed_grid_mesh):
    c = SculptController()
    _attach(c, perturbed_grid_mesh)
    assert c.session is not None
    assert c.session.target.n == perturbed_grid_mesh[0].shape[0]


def test_attach_geometry_auto_sets_default_radius(perturbed_grid_mesh):
    """Without an explicit Brush(), radius adapts to the mesh's edge length."""
    c = SculptController()
    _attach(c, perturbed_grid_mesh)
    vs, fs, _ = perturbed_grid_mesh
    e_all = np.concatenate(
        [
            np.linalg.norm(vs[fs[:, 1]] - vs[fs[:, 0]], axis=1),
            np.linalg.norm(vs[fs[:, 2]] - vs[fs[:, 1]], axis=1),
            np.linalg.norm(vs[fs[:, 0]] - vs[fs[:, 2]], axis=1),
        ]
    )
    mean_edge = float(e_all.mean())
    assert c.brush.radius > 0
    assert abs(c.brush.radius - 8.0 * mean_edge) < 1e-6


def test_explicit_brush_radius_preserved_across_attach(perturbed_grid_mesh):
    c = SculptController(Brush(radius=42.0))
    _attach(c, perturbed_grid_mesh)
    assert c.brush.radius == 42.0


def test_attach_geometry_sets_radius_bounds(perturbed_grid_mesh):
    """Slider bounds adapt so a tiny or huge mesh stays in-range."""
    c = SculptController()
    _attach(c, perturbed_grid_mesh)
    low, high = c.radius_bounds
    assert low > 0.0
    assert low < c.brush.radius < high


def test_radius_upper_bound_tracks_edge_scale_not_diagonal(flat_grid_mesh):
    """A fine mesh with a large extent must not get a near-half-diagonal max.

    Long thin strip: many small triangles spread over a long axis, so half the
    bbox diagonal dwarfs the workable brush size. The upper bound should follow
    the edge-derived default (~10x it), not the diagonal.
    """
    n, dx, width = 400, 10.0, 1.0
    xs = np.arange(n, dtype=np.float64) * dx
    bot = np.stack([xs, np.zeros(n), np.zeros(n)], axis=1)
    top = np.stack([xs, np.full(n, width), np.zeros(n)], axis=1)
    vs = np.vstack([bot, top])
    fs = []
    for i in range(n - 1):
        a, b, c, d = i, i + 1, n + i, n + i + 1
        fs.append([a, b, d])
        fs.append([a, d, c])
    fs = np.asarray(fs, dtype=np.int64)

    c = SculptController()
    c.attach_geometry(_FakeGeometry(vs, fs))
    low, high = c.radius_bounds
    diag = float(np.linalg.norm(vs.max(axis=0) - vs.min(axis=0)))

    assert low < c.brush.radius < high
    assert high < diag * 0.5
    assert high <= c.brush.radius * 10.5


def test_set_tool_validates(perturbed_grid_mesh):
    c = SculptController()
    _attach(c, perturbed_grid_mesh)
    for tool in ("smooth", "grab", "patch"):
        c.set_tool(tool)
        assert c.session.tool == tool


def test_set_radius(perturbed_grid_mesh):
    c = SculptController(Brush(radius=10.0))
    _attach(c, perturbed_grid_mesh)
    c.set_radius(25.0)
    assert c.brush.radius == 25.0


def test_hotkey_changes_tool(perturbed_grid_mesh):
    c = SculptController()
    _attach(c, perturbed_grid_mesh)
    c.handle_hotkey("1")
    assert c.session.tool == "view"
    c.handle_hotkey("2")
    assert c.session.tool == "grab"
    c.handle_hotkey("3")
    assert c.session.tool == "smooth"
    c.handle_hotkey("4")
    assert c.session.tool == "patch"


def test_hotkey_brackets_resize_brush(perturbed_grid_mesh):
    c = SculptController(Brush(radius=10.0))
    _attach(c, perturbed_grid_mesh)
    c.handle_hotkey("]")
    assert c.brush.radius > 10.0
    c.handle_hotkey("[")
    assert abs(c.brush.radius - 10.0) < 1e-9


def test_empty_stack_undo_is_noop(perturbed_grid_mesh):
    c = SculptController()
    _attach(c, perturbed_grid_mesh)
    assert STACK.undo() is None  # nothing pushed; must not raise


def test_grab_stroke_round_trip(perturbed_grid_mesh):
    """Grab a vertex, drag in screen space (via injected MeshHit), commit, undo."""
    vs, fs, interior = perturbed_grid_mesh
    c = SculptController(Brush(radius=0.5))
    geom = _attach(c, perturbed_grid_mesh)
    c.set_tool("grab")

    hit = MeshHit(
        world_position=vs[interior].astype(np.float64),
        normal=np.array([0.0, 0.0, 1.0]),
    )
    c._pick = MagicMock(return_value=hit)
    c._screen_delta_to_world = MagicMock(return_value=np.array([0.0, 0.0, 0.3]))
    c._brush_active = lambda h: __import__(
        "mosaic.sculpt.tools", fromlist=["brush_query"]
    ).brush_query(
        c.session.target.vs,
        h.world_position,
        c.brush.radius,
    )

    c.handle_event(EventKind.LMB_DOWN, 50, 50)
    c.handle_event(EventKind.MOUSE_MOVE, 60, 60)
    c.handle_event(EventKind.LMB_UP, 60, 60)

    target = c.session.target
    assert target.vs[interior, 2] != vs[interior, 2]
    assert STACK.undo() is not None  # stroke pushed an undo entry
    assert np.allclose(target.vs, vs, atol=1e-6)


def test_stroke_undo_targets_live_geometry_after_replacement(perturbed_grid_mesh):
    """Undo must edit the geometry currently under the uuid, not the captured object.

    Reproduces: sculpt -> remove -> undo (restore) -> undo (sculpt). The interactor
    restores a *copy* under the same uuid, so the controller's undo closure must
    resolve the live geometry by uuid rather than mutate the now-orphaned object it
    held a reference to. Otherwise the visible mesh keeps the sculpted edit.
    """
    vs, fs, interior = perturbed_grid_mesh
    c = SculptController(Brush(radius=0.5))
    original = _attach(c, perturbed_grid_mesh)

    # A live container keyed by uuid; the resolver mimics container.get(uuid).
    live = {original.uuid: original}
    c.set_geometry_resolver(lambda u: live.get(u))

    c.set_tool("grab")
    hit = MeshHit(
        world_position=vs[interior].astype(np.float64),
        normal=np.array([0.0, 0.0, 1.0]),
    )
    c._pick = MagicMock(return_value=hit)
    c._screen_delta_to_world = MagicMock(return_value=np.array([0.0, 0.0, 0.3]))
    c._brush_active = lambda h: __import__(
        "mosaic.sculpt.tools", fromlist=["brush_query"]
    ).brush_query(c.session.target.vs, h.world_position, c.brush.radius)

    c.handle_event(EventKind.LMB_DOWN, 50, 50)
    c.handle_event(EventKind.MOUSE_MOVE, 60, 60)
    c.handle_event(EventKind.LMB_UP, 60, 60)
    sculpted_z = original.points[interior, 2]
    assert sculpted_z != pytest.approx(vs[interior, 2])

    # Interactor remove + restore: a copy takes over the uuid, original is orphaned.
    restored = _FakeGeometry(original.points.copy(), fs, uuid=original.uuid)
    live[original.uuid] = restored
    c.release_geometry()

    assert STACK.undo() is not None
    # The live geometry must revert; the orphan is irrelevant.
    assert np.allclose(restored.points[interior, 2], vs[interior, 2], atol=1e-6)


def test_stroke_undo_renders_after_leaving_sculpt_mode(perturbed_grid_mesh):
    """A patch/stroke undo must still trigger a render once sculpt mode is gone.

    The global Ctrl+Z outlives sculpt mode; unbind_renderer nulls the controller's
    live render callback. The undo closure must capture a render trigger at push
    time so the swap is actually painted, not left invisible until the next event.
    """
    vs, fs, interior = perturbed_grid_mesh
    c = SculptController(Brush(radius=0.5))
    _attach(c, perturbed_grid_mesh)

    renders = []
    c._render_callback = lambda: renders.append(1)

    c.set_tool("grab")
    hit = MeshHit(
        world_position=vs[interior].astype(np.float64),
        normal=np.array([0.0, 0.0, 1.0]),
    )
    c._pick = MagicMock(return_value=hit)
    c._screen_delta_to_world = MagicMock(return_value=np.array([0.0, 0.0, 0.3]))
    c._brush_active = lambda h: __import__(
        "mosaic.sculpt.tools", fromlist=["brush_query"]
    ).brush_query(c.session.target.vs, h.world_position, c.brush.radius)

    c.handle_event(EventKind.LMB_DOWN, 50, 50)
    c.handle_event(EventKind.MOUSE_MOVE, 60, 60)
    c.handle_event(EventKind.LMB_UP, 60, 60)

    # Leave sculpt mode: the live render callback is torn down.
    c.unbind_renderer()
    renders.clear()

    assert STACK.undo() is not None
    assert renders, "undo after leaving sculpt mode issued no render"


def test_smooth_stroke_pulls_perturbation_down(perturbed_grid_mesh):
    vs, fs, interior = perturbed_grid_mesh
    c = SculptController(Brush(radius=0.5))
    _attach(c, perturbed_grid_mesh)
    c.set_tool("smooth")

    hit = MeshHit(
        world_position=vs[interior].astype(np.float64),
        normal=np.array([0.0, 0.0, 1.0]),
    )
    c._pick = MagicMock(return_value=hit)

    z_before = c.session.target.vs[interior, 2]
    c.handle_event(EventKind.LMB_DOWN, 100, 100)
    for _ in range(3):
        c.handle_event(EventKind.MOUSE_MOVE, 100, 100)
    c.handle_event(EventKind.LMB_UP, 100, 100)
    z_after = c.session.target.vs[interior, 2]
    assert 0 < z_after < z_before


def test_patch_brush_stroke_closes_hole(punched_grid_mesh):
    """Patch as a brush: paint over the hole rim, release closes it."""
    vs, fs = punched_grid_mesh
    c = SculptController(Brush(radius=0.4))
    geom = _attach(c, punched_grid_mesh)
    c.set_tool("patch")

    hit = MeshHit(
        world_position=np.array([0.5, 0.5, 0.0]),
        normal=np.array([0.0, 0.0, 1.0]),
    )
    c._pick = MagicMock(return_value=hit)
    geom.swap_data = MagicMock()

    n_f_before = len(c.session.target.fs)
    c.handle_event(EventKind.LMB_DOWN, 50, 50)
    # Drag around to accumulate boundary touches.
    c.handle_event(EventKind.MOUSE_MOVE, 50, 50)
    c.handle_event(EventKind.LMB_UP, 50, 50)
    assert len(c.session.target.fs) > n_f_before


def test_patch_brush_no_boundary_touches_does_not_apply(flat_grid_mesh):
    """Releasing a patch stroke that crossed no boundary leaves topology intact."""
    vs, fs = flat_grid_mesh
    c = SculptController(Brush(radius=0.1))
    _attach(c, flat_grid_mesh)
    c.set_tool("patch")

    hit = MeshHit(
        world_position=np.array([0.5, 0.5, 0.0]),
        normal=np.array([0.0, 0.0, 1.0]),
    )
    c._pick = MagicMock(return_value=hit)

    n_f_before = len(c.session.target.fs)
    c.handle_event(EventKind.LMB_DOWN, 50, 50)
    c.handle_event(EventKind.MOUSE_MOVE, 50, 50)
    c.handle_event(EventKind.LMB_UP, 50, 50)
    assert len(c.session.target.fs) == n_f_before


def test_detach_clears_session(perturbed_grid_mesh):
    c = SculptController()
    _attach(c, perturbed_grid_mesh)
    c.detach()
    assert c.session is None


def test_apply_tint_routes_through_geometry_color_points(perturbed_grid_mesh):
    """Tint goes through Geometry.color_points, not a parallel actor."""
    c = SculptController(Brush(radius=0.5))
    geom = _attach(c, perturbed_grid_mesh)
    c.set_tool("grab")

    c._apply_tint(np.array([1, 2, 5], dtype=np.int64))
    assert len(geom.color_calls) == 1
    indices, color = geom.color_calls[0]
    assert sorted(indices.tolist()) == [1, 2, 5]
    # Color matches the grab tool's palette entry.
    assert color == pytest.approx(TOOL_BY_ID["grab"].color, abs=1e-6)


def test_apply_tint_then_clear_resets_base_color(perturbed_grid_mesh):
    """After clearing, set_color() should fire once to restore the mesh."""
    c = SculptController(Brush(radius=0.5))
    geom = _attach(c, perturbed_grid_mesh)
    c.set_tool("grab")

    c._apply_tint(np.array([3, 7], dtype=np.int64))
    assert geom.set_color_calls == 0

    c._clear_tint()
    assert geom.set_color_calls == 1

    # Idempotent: a second clear shouldn't keep calling set_color.
    c._clear_tint()
    assert geom.set_color_calls == 1


def test_tool_switch_updates_tint_color(perturbed_grid_mesh):
    """Each tool tints with its own color; switching tools updates the color."""
    c = SculptController(Brush(radius=0.5))
    geom = _attach(c, perturbed_grid_mesh)

    c.set_tool("grab")
    c._apply_tint(np.array([0], dtype=np.int64))
    _, grab_color = geom.color_calls[-1]

    c.set_tool("smooth")
    c._apply_tint(np.array([0], dtype=np.int64))
    _, smooth_color = geom.color_calls[-1]

    assert grab_color != smooth_color


def test_view_tool_does_not_sculpt(perturbed_grid_mesh):
    """LMB while in View tool must not move any vertices."""
    vs, fs, _ = perturbed_grid_mesh
    c = SculptController(Brush(radius=0.5))
    _attach(c, perturbed_grid_mesh)
    c.set_tool("view")

    hit = MeshHit(
        world_position=np.array([0.5, 0.5, 0.0]),
        normal=np.array([0.0, 0.0, 1.0]),
    )
    c._pick = MagicMock(return_value=hit)

    before = c.session.target.vs.copy()
    c.handle_event(EventKind.LMB_DOWN, 50, 50)
    c.handle_event(EventKind.MOUSE_MOVE, 60, 60)
    c.handle_event(EventKind.LMB_UP, 60, 60)
    assert np.array_equal(c.session.target.vs, before)
    assert STACK.undo() is None  # no-op stroke pushed nothing
