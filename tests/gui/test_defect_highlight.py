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
