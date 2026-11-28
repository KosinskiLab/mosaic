import numpy as np
import open3d as o3d
import vtk

from mosaic.meshing.check import check_mesh
from mosaic.widgets.defect_highlight import DefectHighlight


def _holed_sphere():
    sphere = o3d.geometry.TriangleMesh.create_sphere(radius=10, resolution=10)
    vs, fs = np.asarray(sphere.vertices), np.asarray(sphere.triangles)[1:]
    return vs, fs, check_mesh(vs, fs)[0]


def test_show_adds_one_actor_and_hide_removes_it():
    renderer = vtk.vtkRenderer()
    vs, fs, defect = _holed_sphere()
    highlight = DefectHighlight(renderer)
    highlight.show(vs, fs, defect)
    assert renderer.GetActors().GetNumberOfItems() == 1
    assert highlight.defect is defect
    highlight.hide()
    assert renderer.GetActors().GetNumberOfItems() == 0
    assert highlight.defect is None


def test_showing_another_defect_replaces_the_patch():
    renderer = vtk.vtkRenderer()
    vs, fs, defect = _holed_sphere()
    highlight = DefectHighlight(renderer)
    highlight.show(vs, fs, defect)
    highlight.show(vs, fs, defect)
    assert renderer.GetActors().GetNumberOfItems() == 1


def test_camera_looks_at_the_defect_from_outside():
    renderer = vtk.vtkRenderer()
    vs, fs, defect = _holed_sphere()
    DefectHighlight(renderer).show(vs, fs, defect)
    camera = renderer.GetActiveCamera()
    target = vs[defect.vertices].mean(0)
    np.testing.assert_allclose(camera.GetFocalPoint(), target, atol=1e-6)
    outward = target - vs.mean(0)
    assert np.dot(np.subtract(camera.GetPosition(), target), outward) > 0


def test_camera_backs_off_from_a_hole_in_the_middle_of_a_sheet():
    n = 11
    xs, ys = np.meshgrid(np.arange(n, dtype=float), np.arange(n, dtype=float))
    vs = np.stack([xs.ravel(), ys.ravel(), np.zeros(n * n)], axis=1)
    fs = []
    for i in range(n - 1):
        for j in range(n - 1):
            if 4 <= i <= 5 and 4 <= j <= 5:
                continue
            a, b, c, d = i * n + j, i * n + j + 1, (i + 1) * n + j, (i + 1) * n + j + 1
            fs += [[a, b, d], [a, d, c]]
    fs = np.array(fs)
    defect = check_mesh(vs, fs)[0]
    renderer = vtk.vtkRenderer()
    DefectHighlight(renderer).show(vs, fs, defect)
    camera = renderer.GetActiveCamera()
    offset = np.subtract(camera.GetPosition(), camera.GetFocalPoint())
    assert np.linalg.norm(offset) > 1


def _app_with_highlight(qapp):
    from types import SimpleNamespace

    from mosaic.geometry import Geometry
    from mosaic.meshing.utils import to_open3d
    from mosaic.parametrization import TriangularMesh

    vs, fs, defect = _holed_sphere()
    model = TriangularMesh(to_open3d(vs, fs), repair=False)
    geometry = Geometry(points=vs, model=model)
    highlight = DefectHighlight(vtk.vtkRenderer())
    highlight.show(vs, fs, defect)

    def pane(data):
        return SimpleNamespace(
            container=SimpleNamespace(data=data),
            data_list=SimpleNamespace(set_active_defect=lambda geometry: None),
        )

    app = SimpleNamespace(
        defect_highlight=highlight,
        _defect_source=(geometry, model),
        cdata=SimpleNamespace(data=pane([]), models=pane([geometry])),
    )
    return app, geometry


def test_highlight_stays_while_its_mesh_is_unchanged(qapp):
    from mosaic.gui import App

    app, _ = _app_with_highlight(qapp)
    App._drop_stale_defect(app)
    assert app.defect_highlight.defect is not None


def test_highlight_goes_with_its_removed_mesh(qapp):
    from mosaic.gui import App

    app, _ = _app_with_highlight(qapp)
    app.cdata.models.container.data.clear()
    App._drop_stale_defect(app)
    assert app.defect_highlight.defect is None


def test_highlight_goes_when_its_mesh_is_replaced(qapp):
    from mosaic.gui import App
    from mosaic.meshing.utils import to_open3d
    from mosaic.parametrization import TriangularMesh

    app, geometry = _app_with_highlight(qapp)
    vs, fs, _ = _holed_sphere()
    geometry.swap_data(points=vs, faces=fs, model=TriangularMesh(to_open3d(vs, fs)))
    App._drop_stale_defect(app)
    assert app.defect_highlight.defect is None
