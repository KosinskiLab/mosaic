"""Functional tests: merge + remove_selection push undo entries that restore state."""

from unittest.mock import Mock

import numpy as np
import pytest

from mosaic.commands.session import Session
from mosaic.geometry import Geometry
from mosaic.interactor import DataContainerInteractor
from mosaic.swaps import GeometrySubset, GeometrySwap
from mosaic.undo import STACK

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def _reset_stack():
    STACK.clear()
    yield
    STACK.clear()


def _points(n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.uniform(0.0, 1.0, size=(n, 3)).astype(np.float64)


@pytest.fixture
def interactor(qapp):
    session = Session(quiet=True)
    ci = DataContainerInteractor(session, role="data")
    mock_vp = Mock()
    mock_vp.render.return_value = None
    mock_vp.render_vtk.return_value = None
    mock_vp.rendered_actors = Mock()
    ci.attach_viewport(mock_vp)
    return ci


def _select_points(interactor, geom, ids):
    interactor.point_selection = {geom.uuid: np.asarray(ids, dtype=np.int64)}


def _add(interactor, n: int, seed: int) -> Geometry:
    geom = Geometry(points=_points(n, seed))
    interactor.add(geom)
    # update() populates the tree widget so set_selection_by_uuid works
    interactor.update()
    return interactor.container.get(geom.uuid)


def test_merge_undo_restores_originals(interactor):
    g1 = _add(interactor, 50, seed=1)
    g2 = _add(interactor, 30, seed=2)
    interactor.set_selection_by_uuid([g1.uuid, g2.uuid])

    interactor.merge()
    assert interactor.container.get(g1.uuid) is None
    assert interactor.container.get(g2.uuid) is None

    STACK.undo()
    assert interactor.container.get(g1.uuid) is not None
    assert interactor.container.get(g2.uuid) is not None
    assert interactor.container.get(g1.uuid).get_number_of_points() == 50


def test_merge_redo_replays(interactor):
    g1 = _add(interactor, 50, seed=1)
    g2 = _add(interactor, 30, seed=2)
    interactor.set_selection_by_uuid([g1.uuid, g2.uuid])
    interactor.merge()
    STACK.undo()

    STACK.redo()
    assert interactor.container.get(g1.uuid) is None
    assert interactor.container.get(g2.uuid) is None


def test_remove_selection_undo_restores(interactor):
    g1 = _add(interactor, 50, seed=1)
    interactor.set_selection_by_uuid([g1.uuid])

    interactor.remove_selection()
    assert interactor.container.get(g1.uuid) is None

    STACK.undo()
    restored = interactor.container.get(g1.uuid)
    assert restored is not None
    assert restored.get_number_of_points() == 50


def test_remove_point_selection_undo_restores_full_count(interactor):
    g1 = _add(interactor, 50, seed=1)
    _select_points(interactor, g1, [0, 1, 2])

    interactor.remove_selection()
    assert interactor.container.get(g1.uuid).get_number_of_points() == 47

    STACK.undo()
    assert interactor.container.get(g1.uuid).get_number_of_points() == 50


def test_remove_point_selection_redo_reshrinks(interactor):
    g1 = _add(interactor, 50, seed=1)
    _select_points(interactor, g1, [0, 1, 2])
    interactor.remove_selection()
    STACK.undo()

    STACK.redo()
    assert interactor.container.get(g1.uuid).get_number_of_points() == 47


def test_remove_point_selection_stores_sparse_record(interactor):
    g1 = _add(interactor, 5000, seed=1)
    _select_points(interactor, g1, [10, 11, 12, 13])

    captured = {}
    original = interactor._push_swap

    def spy(label, changes):
        captured["changes"] = changes
        return original(label, changes)

    interactor._push_swap = spy
    interactor.remove_selection()

    removals = [c for c in captured["changes"] if isinstance(c, GeometrySubset)]
    assert len(removals) == 1
    assert removals[0].removed.get_number_of_points() == 4


def test_remove_all_points_routes_through_full_swap(interactor):
    g1 = _add(interactor, 30, seed=2)
    _select_points(interactor, g1, list(range(30)))

    captured = {}
    original = interactor._push_swap

    def spy(label, changes):
        captured["changes"] = changes
        return original(label, changes)

    interactor._push_swap = spy
    interactor.remove_selection()
    assert interactor.container.get(g1.uuid) is None

    swaps = [c for c in captured["changes"] if isinstance(c, GeometrySwap)]
    subsets = [c for c in captured["changes"] if isinstance(c, GeometrySubset)]
    assert any(s.uuid == g1.uuid for s in swaps)
    assert len(subsets) == 0

    STACK.undo()
    restored = interactor.container.get(g1.uuid)
    assert restored is not None
    assert restored.get_number_of_points() == 30


def test_merge_point_selection_undo_restores_source(interactor):
    g1 = _add(interactor, 50, seed=1)
    _select_points(interactor, g1, [0, 1, 2, 3, 4])
    baseline = len(interactor.container)

    interactor.merge()
    assert interactor.container.get(g1.uuid).get_number_of_points() == 45

    STACK.undo()
    assert interactor.container.get(g1.uuid).get_number_of_points() == 50
    assert len(interactor.container) == baseline


def test_merge_single_selection_undo_does_not_delete(interactor):
    g1 = _add(interactor, 40, seed=3)
    interactor.set_selection_by_uuid([g1.uuid])
    baseline = len(interactor.container)

    interactor.merge()

    STACK.undo()
    restored = interactor.container.get(g1.uuid)
    assert restored is not None
    assert restored.get_number_of_points() == 40
    assert len(interactor.container) == baseline


def test_mixed_merge_undo_redo(interactor):
    g1 = _add(interactor, 50, seed=1)
    g2 = _add(interactor, 30, seed=2)
    interactor.set_selection_by_uuid([g1.uuid])
    _select_points(interactor, g2, [0, 1, 2])
    baseline = len(interactor.container)

    interactor.merge()
    assert interactor.container.get(g1.uuid) is None
    assert interactor.container.get(g2.uuid).get_number_of_points() == 27

    STACK.undo()
    assert interactor.container.get(g1.uuid).get_number_of_points() == 50
    assert interactor.container.get(g2.uuid).get_number_of_points() == 30
    assert len(interactor.container) == baseline

    STACK.redo()
    assert interactor.container.get(g1.uuid) is None
    assert interactor.container.get(g2.uuid).get_number_of_points() == 27


def test_undo_restore_preserves_base_color_in_entity_mode(interactor):
    interactor.set_coloring_mode("entity")
    g1 = _add(interactor, 20, seed=1)
    original = interactor.container.get(g1.uuid)._appearance["base_color"]
    interactor.set_selection_by_uuid([g1.uuid])

    interactor.remove_selection()
    STACK.undo()

    restored = interactor.container.get(g1.uuid)
    assert restored is not None
    assert restored._appearance["base_color"] == original


def _add_mesh(interactor):
    """A quad split into two triangles sharing the 1-2 edge."""
    from mosaic.meshing.utils import to_open3d
    from mosaic.parametrization import TriangularMesh

    vertices = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0]]
    )
    faces = np.array([[0, 1, 2], [1, 3, 2]])
    model = TriangularMesh(to_open3d(vertices, faces), repair=False)
    geom = Geometry(points=vertices, model=model)
    geom.change_representation("mesh")
    interactor.add(geom)
    interactor.update()
    return interactor.container.get(geom.uuid)


def test_remove_mesh_point_selection_restores_connectivity(interactor):
    mesh = _add_mesh(interactor)
    # Removing vertex 3 severs triangle [1, 3, 2]; the subset/merge undo path
    # would drop that straddling face and never restore it.
    _select_points(interactor, mesh, [3])

    interactor.remove_selection()
    survivor = interactor.container.get(mesh.uuid)
    assert survivor.get_number_of_points() == 3
    assert len(survivor.model.triangles) == 1

    STACK.undo()
    restored = interactor.container.get(mesh.uuid)
    assert restored.get_number_of_points() == 4
    assert len(restored.model.triangles) == 2


def test_remove_mesh_point_selection_routes_through_swap(interactor):
    mesh = _add_mesh(interactor)
    _select_points(interactor, mesh, [3])

    captured = {}
    original = interactor._push_swap

    def spy(label, changes):
        captured["changes"] = changes
        return original(label, changes)

    interactor._push_swap = spy
    interactor.remove_selection()

    subsets = [c for c in captured["changes"] if isinstance(c, GeometrySubset)]
    swaps = [c for c in captured["changes"] if isinstance(c, GeometrySwap)]
    assert len(subsets) == 0
    assert any(s.uuid == mesh.uuid for s in swaps)


def test_remove_mesh_point_selection_redo_reshrinks(interactor):
    mesh = _add_mesh(interactor)
    _select_points(interactor, mesh, [3])
    interactor.remove_selection()
    STACK.undo()

    STACK.redo()
    survivor = interactor.container.get(mesh.uuid)
    assert survivor.get_number_of_points() == 3
    assert len(survivor.model.triangles) == 1


def test_merge_mesh_point_selection_undo_restores_connectivity(interactor):
    mesh = _add_mesh(interactor)
    _select_points(interactor, mesh, [3])

    interactor.merge()
    assert interactor.container.get(mesh.uuid).get_number_of_points() == 3

    STACK.undo()
    restored = interactor.container.get(mesh.uuid)
    assert restored.get_number_of_points() == 4
    assert len(restored.model.triangles) == 2


def _add_segmentation(interactor, n: int, seed: int):
    from mosaic.geometry import SegmentationGeometry

    seg = SegmentationGeometry(
        points=_points(n, seed).astype(np.float32), sampling_rate=1.0
    )
    interactor.add(seg)
    interactor.update()
    return interactor.container.get(seg.uuid)


def test_remove_point_selection_preserves_segmentation_type(interactor):
    from mosaic.geometry import SegmentationGeometry

    seg = _add_segmentation(interactor, 60, seed=4)
    n_before = seg.get_number_of_points()
    _select_points(interactor, seg, [0, 1, 2])

    interactor.remove_selection()
    STACK.undo()

    restored = interactor.container.get(seg.uuid)
    assert isinstance(restored, SegmentationGeometry)
    assert restored._representation == "segmentation"
    assert restored.get_number_of_points() == n_before


def test_merge_whole_segmentations_preserves_type(interactor):
    from mosaic.geometry import SegmentationGeometry

    s1 = _add_segmentation(interactor, 60, seed=4)
    s2 = _add_segmentation(interactor, 40, seed=5)
    interactor.set_selection_by_uuid([s1.uuid, s2.uuid])

    interactor.merge()

    survivors = [interactor.container.get(i) for i in range(len(interactor.container))]
    survivors = [g for g in survivors if g is not None]
    assert len(survivors) == 1
    assert isinstance(survivors[0], SegmentationGeometry)
    assert survivors[0]._representation == "segmentation"
