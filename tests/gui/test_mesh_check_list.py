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
    rect = tree.visualItemRect(tree.topLevelItem(row))
    pos = QPointF(rect.left() + 16, rect.center().y())
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
    assert launched == [big] and big._defects is None


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


def test_unticking_the_shown_kind_hides_the_highlight(qapp, all_kinds_shown):
    import vtk

    from mosaic.gui import build_mesh_check_menu
    from mosaic.widgets.defect_highlight import DefectHighlight

    model = _holed_mesh()
    highlight = DefectHighlight(vtk.vtkRenderer())
    highlight.show(model.vertices, model.triangles, model.defects[0])
    menu = build_mesh_check_menu(None, highlight, refresh=lambda: None)
    holes = next(a for a in menu.actions() if a.text() == "Holes")
    holes.trigger()
    assert highlight.defect is None
    assert Settings.ui.mesh_check_holes is False
    assert shown_defects(model) == []


def test_ticking_again_restores_without_rechecking(qapp, all_kinds_shown, monkeypatch):
    import vtk

    from mosaic import meshing
    from mosaic.gui import build_mesh_check_menu
    from mosaic.widgets.defect_highlight import DefectHighlight

    model = _holed_mesh()
    expected = model.defects
    monkeypatch.setattr(meshing, "check_mesh", lambda *a, **k: pytest.fail())
    menu = build_mesh_check_menu(
        None, DefectHighlight(vtk.vtkRenderer()), refresh=lambda: None
    )
    holes = next(a for a in menu.actions() if a.text() == "Holes")
    holes.trigger()
    holes.trigger()
    assert shown_defects(model) == expected


def test_deleting_a_triangle_repaints_the_list(qapp, all_kinds_shown):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from qtpy.QtCore import QObject

    from mosaic.commands.session import Session
    from mosaic.interactor import DataContainerInteractor
    from mosaic.styles import MeshEditInteractorStyle

    pane = DataContainerInteractor(Session(quiet=True), role="models")
    viewport = Mock()
    viewport.render.side_effect = lambda **kwargs: pane.data_list.update(
        pane._uuid_to_items()
    )
    pane.attach_viewport(viewport)
    vs, fs = _sphere()
    geometry = Geometry(points=vs, model=TriangularMesh(to_open3d(vs, fs)))
    geometry.change_representation("mesh")
    pane.add(geometry)
    pane.render()
    pane.data_list.resize(260, 200)
    pane.data_list.show()
    qapp.processEvents()

    class Paints(QObject):
        count = 0

        def eventFilter(self, obj, event):
            self.count += event.type() == QEvent.Type.Paint
            return False

    paints = Paints()
    pane.data_list.tree_widget.viewport().installEventFilter(paints)
    geometry = pane.container.data[0]
    face = geometry._data.GetVerts().GetNumberOfCells() + 5
    style = SimpleNamespace(
        selected_faces=[{"geometry": geometry, "cell_id": face}],
        models_pane=pane,
        cleanup=lambda: None,
    )
    MeshEditInteractorStyle.remove_selected(style)
    qapp.processEvents()
    assert shown_defects(geometry.model)
    assert paints.count > 0
