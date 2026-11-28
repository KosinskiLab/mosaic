import numpy as np
import open3d as o3d
import pytest
from qtpy.QtCore import QEvent, QPointF, Qt
from qtpy.QtGui import QMouseEvent
from qtpy.QtWidgets import QApplication

from mosaic.geometry import Geometry
from mosaic.meshing.utils import to_open3d
from mosaic.parametrization import TriangularMesh
from mosaic.settings import Settings
from mosaic.widgets import container_list
from mosaic.widgets.container_list import (
    ContainerTreeWidget,
    StyledTreeWidgetItem,
    shown_defects,
)


def _sphere(resolution=10):
    sphere = o3d.geometry.TriangleMesh.create_sphere(radius=10, resolution=resolution)
    return np.asarray(sphere.vertices), np.asarray(sphere.triangles)


def _holed_mesh():
    vs, fs = _sphere()
    return TriangularMesh(to_open3d(vs, fs[1:]), repair=False)


@pytest.fixture
def all_kinds_shown():
    names = ("mesh_check_holes", "mesh_check_twisted", "mesh_check_nonmanifold")
    before = {name: getattr(Settings.ui, name) for name in names}
    for name in names:
        setattr(Settings.ui, name, True)
    yield
    for name, value in before.items():
        setattr(Settings.ui, name, value)


def _press_icon(widget, row):
    tree = widget.tree_widget
    rect = container_list._defect_icon_rect(tree.visualItemRect(tree.topLevelItem(row)))
    pos = QPointF(rect.center())
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos,
        tree.viewport().mapToGlobal(pos.toPoint()).toPointF(),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(tree.viewport(), event)


def test_point_cloud_has_no_defects(qapp, all_kinds_shown):
    geometry = Geometry(points=np.random.default_rng(0).random((20, 3)))
    assert shown_defects(geometry.model) == []


def test_holed_mesh_shows_its_hole(qapp, all_kinds_shown):
    assert [d.kind for d in shown_defects(_holed_mesh())] == ["hole"]


def test_unticked_kind_is_not_shown(qapp, all_kinds_shown):
    Settings.ui.mesh_check_holes = False
    assert shown_defects(_holed_mesh()) == []


def test_large_mesh_is_not_checked_while_painting(qapp, all_kinds_shown, monkeypatch):
    launched = []
    monkeypatch.setattr(container_list, "_check_in_background", launched.append)
    big = TriangularMesh(to_open3d(*_sphere(resolution=320)), repair=False)
    assert shown_defects(big) == []
    assert launched == [big] and "defects" not in big.__dict__


def test_choosing_a_defect_emits_it(qapp, all_kinds_shown):
    model = _holed_mesh()
    geometry = Geometry(points=model.vertices, model=model)
    geometry.change_representation("mesh")
    widget = ContainerTreeWidget()
    widget.resize(260, 200)
    widget.show()
    widget.tree_widget.addTopLevelItem(StyledTreeWidgetItem(geometry=geometry))
    received = []
    widget.defect_requested.connect(lambda g, d: received.append((g, d)))
    _press_icon(widget, row=0)
    widget._defect_menu.actions()[0].trigger()
    assert received == [(geometry, model.defects[0])]


def test_active_row_offers_hide(qapp, all_kinds_shown):
    model = _holed_mesh()
    geometry = Geometry(points=model.vertices, model=model)
    geometry.change_representation("mesh")
    widget = ContainerTreeWidget()
    widget.resize(260, 200)
    widget.show()
    widget.tree_widget.addTopLevelItem(StyledTreeWidgetItem(geometry=geometry))
    hidden = []
    widget.defect_hidden.connect(lambda: hidden.append(True))
    widget.set_active_defect(geometry)
    _press_icon(widget, row=0)
    widget._defect_menu.actions()[0].trigger()
    assert hidden == [True]
