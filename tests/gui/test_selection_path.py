"""
Functional tests for the work done per selection and per picking-mode event.

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from unittest.mock import Mock

import numpy as np
import pytest
from qtpy.QtCore import QEvent, QPointF, Qt
from qtpy.QtGui import QMouseEvent

from mosaic.commands.session import Session
from mosaic.geometry import Geometry
from mosaic.interactor import DataContainerInteractor
from mosaic.viewport import ViewportInteractor

pytestmark = pytest.mark.gui


@pytest.fixture
def interactor(qapp):
    session = Session(quiet=True)
    ci = DataContainerInteractor(session, role="data")
    viewport = Mock()
    viewport.render.return_value = None
    viewport.render_vtk.return_value = None
    ci.attach_viewport(viewport)
    return ci


def _add(interactor, seed):
    rng = np.random.default_rng(seed)
    geometry = Geometry(points=rng.uniform(0, 1, size=(20, 3)))
    interactor.add(geometry)
    interactor.update()
    return interactor.container.get(geometry.uuid)


def _count_renders(interactor, monkeypatch):
    calls = []
    monkeypatch.setattr(interactor, "render_vtk", lambda: calls.append(1))
    return calls


def _record_colors(geometries, monkeypatch):
    colors = {}
    for geometry in geometries:
        monkeypatch.setattr(
            geometry,
            "set_color",
            lambda color=None, g=geometry: colors.__setitem__(g.uuid, color),
        )
    return colors


def test_set_selection_by_uuid_renders_once(interactor, monkeypatch):
    first, second = _add(interactor, 1), _add(interactor, 2)
    renders = _count_renders(interactor, monkeypatch)

    interactor.set_selection_by_uuid([first.uuid])

    assert len(renders) == 1
    assert interactor._get_selected_uuids() == [first.uuid]
    assert second.uuid not in interactor._get_selected_uuids()


def test_set_selection_by_uuid_highlights_the_geometry(interactor, monkeypatch):
    first, second = _add(interactor, 1), _add(interactor, 2)
    colors = _record_colors((first, second), monkeypatch)

    interactor.set_selection_by_uuid([first.uuid])

    highlight = first._appearance.get(
        "highlight_color", interactor.container.highlight_color
    )
    assert colors == {first.uuid: highlight}
    assert interactor.container._highlighted_uuids == {first.uuid}


def test_pick_prop_renders_once_per_hit(interactor, monkeypatch):
    geometry = _add(interactor, 1)
    renders = _count_renders(interactor, monkeypatch)

    interactor.pick_prop(geometry.actor)

    assert len(renders) == 1
    assert interactor._get_selected_uuids() == [geometry.uuid]


def test_pick_prop_on_unknown_prop_does_nothing(interactor, monkeypatch):
    _add(interactor, 1)
    renders = _count_renders(interactor, monkeypatch)

    interactor.pick_prop(None)

    assert renders == []
    assert interactor._get_selected_uuids() == []


def test_clearing_the_selection_unhighlights(interactor, monkeypatch):
    first = _add(interactor, 1)
    interactor.set_selection_by_uuid([first.uuid])
    colors = _record_colors((first,), monkeypatch)

    interactor.set_selection_by_uuid([])

    base = first._appearance.get("base_color", interactor.container.base_color)
    assert colors == {first.uuid: base}
    assert interactor.container._highlighted_uuids == set()


def test_sidebar_selection_still_highlights(interactor, monkeypatch):
    first = _add(interactor, 1)
    _add(interactor, 2)
    renders = _count_renders(interactor, monkeypatch)

    # A sidebar click selects the tree item; the interactor must still pick
    # that up through itemSelectionChanged.
    for item, _, _ in interactor.data_list.traverse():
        if item.metadata.get("uuid") == first.uuid:
            item.setSelected(True)

    assert len(renders) == 1
    assert interactor.container._highlighted_uuids == {first.uuid}


class _StubVTKWidget:
    """Widget stand-in exposing only what the viewport event filter touches."""

    def __init__(self):
        self.devicePixelRatio = Mock(return_value=2.0)
        self.height = Mock(return_value=500)


def _viewport_in_mode(mode, monkeypatch):
    viewport = ViewportInteractor.__new__(ViewportInteractor)
    viewport.vtk_widget = _StubVTKWidget()
    viewport._interaction_mode = mode
    viewport._world_picker = Mock()
    viewport.current_target = Mock()
    monkeypatch.setattr(viewport, "_pick_prop_at", Mock(return_value="prop"))
    monkeypatch.setattr(
        viewport, "get_event_position", Mock(return_value=((1.0, 2.0, 3.0), None))
    )
    return viewport


def _move_event():
    return QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(100.0, 200.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def test_picking_skips_the_world_position_pick(qapp, monkeypatch):
    viewport = _viewport_in_mode("pick", monkeypatch)

    assert viewport.eventFilter(viewport.vtk_widget, _move_event()) is True

    viewport.get_event_position.assert_not_called()
    viewport._world_picker.Pick.assert_not_called()
    viewport.current_target.pick_prop.assert_called_once_with("prop")
    # display coordinates are x * dpr and (height - y) * dpr
    assert viewport._pick_prop_at.call_args[0][0] == (200.0, 600.0, 0)


def test_drawing_still_resolves_a_world_position(qapp, monkeypatch):
    viewport = _viewport_in_mode("draw", monkeypatch)

    assert viewport.eventFilter(viewport.vtk_widget, _move_event()) is True

    viewport.get_event_position.assert_called_once()
    viewport.current_target.add_point.assert_called_once_with((1.0, 2.0, 3.0))
