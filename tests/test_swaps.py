"""Functional tests for the Qt-free swap helpers operating on a target."""

import numpy as np

from mosaic.container import DataContainer
from mosaic.geometry import Geometry
from mosaic.swaps import GeometrySwap, apply_changes


class _Target:
    """Minimal non-rendering target wrapping a DataContainer."""

    def __init__(self, container):
        self.container = container

    def add(self, geom, *args, **kwargs):
        self.container.add(geom)

    def apply(self, changes, *, undo):
        apply_changes(self, changes, undo=undo)


def _geom(n, seed):
    rng = np.random.default_rng(seed)
    return Geometry(points=rng.uniform(0, 1, size=(n, 3)).astype(np.float64))


def test_apply_changes_add_then_undo_removes():
    target = _Target(DataContainer())
    g = _geom(10, 1)
    change = GeometrySwap(g.uuid, before=None, after=g)

    apply_changes(target, [change], undo=False)
    assert target.container.get(g.uuid) is not None

    apply_changes(target, [change], undo=True)
    assert target.container.get(g.uuid) is None


from mosaic.swaps import build_changes, place
from mosaic.undo import STACK


def test_place_add_records_entry_and_undo_removes():
    STACK.clear()
    target = _Target(DataContainer())
    g = _geom(6, 1)

    placed = place(target, add=[g], label="Add")
    assert placed == [g]
    assert target.container.get(g.uuid) is not None

    STACK.undo()
    assert target.container.get(g.uuid) is None
    STACK.clear()


def test_place_remove_and_add_is_one_reversible_entry():
    STACK.clear()
    target = _Target(DataContainer())
    src = _geom(5, 1)
    target.add(src)
    child_a, child_b = _geom(3, 2), _geom(3, 3)

    place(target, add=[child_a, child_b], remove=[src], label="Cluster")
    assert target.container.get(src.uuid) is None
    assert target.container.get(child_a.uuid) is not None
    assert target.container.get(child_b.uuid) is not None

    STACK.undo()
    assert target.container.get(src.uuid) is not None
    assert target.container.get(child_a.uuid) is None
    assert target.container.get(child_b.uuid) is None
    STACK.clear()
