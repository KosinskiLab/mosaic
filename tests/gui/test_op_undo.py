"""GUI operation callbacks place results through the chokepoint and are undoable."""

from unittest.mock import Mock

import numpy as np
import pytest

from mosaic.commands.session import Session
from mosaic.geometry import Geometry
from mosaic.interactor import DataContainerInteractor
from mosaic.swaps import place
from mosaic.undo import STACK

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def _reset_stack():
    STACK.clear()
    yield
    STACK.clear()


@pytest.fixture
def interactor(qapp):
    session = Session(quiet=True)
    ci = DataContainerInteractor(session, role="data")
    vp = Mock()
    vp.render.return_value = None
    vp.render_vtk.return_value = None
    vp.rendered_actors = Mock()
    ci.attach_viewport(vp)
    return ci


def _geom(n, seed):
    rng = np.random.default_rng(seed)
    return Geometry(points=rng.uniform(0, 1, size=(n, 3)).astype(np.float64))


def test_place_add_through_interactor_is_undoable(interactor):
    result = _geom(9, 2)
    place(interactor, add=[result], label="Smooth")

    assert interactor.container.get(result.uuid) is not None
    STACK.undo()
    assert interactor.container.get(result.uuid) is None


from mosaic.swaps import place as _place  # noqa: F401  (path sanity)


def test_distance_crop_is_undoable(interactor):
    from types import SimpleNamespace

    from mosaic.tabs.segmentation import SegmentationTab

    source = Geometry(
        points=np.array([[0, 0, 0], [0.1, 0, 0], [9, 9, 9]], dtype=np.float64)
    )
    target = Geometry(points=np.array([[0, 0, 0]], dtype=np.float64))
    interactor.add(source)
    interactor.add(target)
    interactor.update()

    stub = SimpleNamespace(cdata=SimpleNamespace(data=interactor))
    n_before = len(interactor.container.data)

    SegmentationTab._apply_distance_crop(
        stub,
        {
            "sources": [interactor.container.get(source.uuid)],
            "targets": [interactor.container.get(target.uuid)],
            "distance": 1.0,
            "keep_smaller": True,
        },
    )

    assert len(interactor.container.data) == n_before + 1
    STACK.undo()
    assert len(interactor.container.data) == n_before


def test_replace_style_place_removes_source_and_undo_restores(interactor):
    src = _geom(8, 1)
    interactor.add(src)
    interactor.update()
    child_a, child_b = _geom(4, 2), _geom(4, 3)

    place(interactor, add=[child_a, child_b], remove=[src], label="Cluster")
    assert interactor.container.get(src.uuid) is None
    assert interactor.container.get(child_a.uuid) is not None

    STACK.undo()
    assert interactor.container.get(src.uuid) is not None
    assert interactor.container.get(child_a.uuid) is None
    assert interactor.container.get(child_b.uuid) is None
