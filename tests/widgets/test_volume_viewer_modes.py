"""Tests for VolumeViewer mode behaviour and renderer strategy split."""

import vtk
import pytest

from mosaic.widgets.volume_viewer import VolumeViewer


@pytest.fixture
def viewer(qapp, fake_vtk_widget):
    return VolumeViewer(fake_vtk_widget)


def test_default_mode_is_2d(viewer):
    assert viewer.mode == "2D"


def test_2d_actor_attached_after_load(viewer, small_volume):
    viewer.swap_volume(small_volume)
    renderer = viewer.renderer
    # The slice actor must be in the renderer when the viewer is in 2D.
    found = False
    props = renderer.GetViewProps()
    props.InitTraversal()
    for _ in range(props.GetNumberOfItems()):
        prop = props.GetNextProp()
        if isinstance(prop, vtk.vtkImageSlice):
            found = True
            break
    assert found, "Expected vtkImageSlice attached to renderer in 2D mode"


def test_volume3d_opacity_ramps_from_low_to_high():
    """The derived opacity transfer function must clamp at 0 below `lo`
    and 1 above `hi`, and rise monotonically between."""
    from mosaic.widgets.volume_viewer import _Volume3DRenderer

    r = _Volume3DRenderer()
    otf = r._build_opacity_tf(lo=0.2, hi=0.8, gamma=1.0)

    assert otf.GetValue(0.0) == pytest.approx(0.0, abs=1e-6)
    assert otf.GetValue(0.2) == pytest.approx(0.0, abs=1e-6)
    assert otf.GetValue(0.8) == pytest.approx(1.0, abs=1e-6)
    assert otf.GetValue(1.0) == pytest.approx(1.0, abs=1e-6)
    assert 0.0 < otf.GetValue(0.5) < 1.0


def test_volume3d_opacity_gamma_curves_the_ramp():
    """A gamma > 1 must push the midpoint below the linear midpoint."""
    from mosaic.widgets.volume_viewer import _Volume3DRenderer

    r = _Volume3DRenderer()
    otf_linear = r._build_opacity_tf(lo=0.0, hi=1.0, gamma=1.0)
    otf_curved = r._build_opacity_tf(lo=0.0, hi=1.0, gamma=2.0)
    assert otf_curved.GetValue(0.5) < otf_linear.GetValue(0.5)


def test_toggle_mode_swaps_actors(viewer, small_volume):
    """Toggling to 3D must detach the slice actor and attach the volume actor."""
    import vtk as _vtk

    viewer.swap_volume(small_volume)
    viewer._toggle_mode()

    assert viewer.mode == "3D"
    found_volume = False
    found_slice = False
    props = viewer.renderer.GetViewProps()
    props.InitTraversal()
    for _ in range(props.GetNumberOfItems()):
        prop = props.GetNextProp()
        if isinstance(prop, _vtk.vtkVolume):
            found_volume = True
        if isinstance(prop, _vtk.vtkImageSlice):
            found_slice = True
    assert found_volume and not found_slice


def test_toggle_mode_emits_signal(viewer, small_volume):
    viewer.swap_volume(small_volume)
    received = []
    viewer.mode_changed.connect(received.append)
    viewer._toggle_mode()
    viewer._toggle_mode()
    assert received == ["3D", "2D"]


def test_toggle_mode_preserves_slice_orientation_projection(viewer, small_volume):
    """Slice / orientation / projection state must survive 3D -> 2D round-trip."""
    viewer.swap_volume(small_volume)
    viewer.orientation_selector.setCurrentText("Y")
    viewer.set_slice(3)
    viewer.project_selector.setCurrentText("Project +")

    viewer._toggle_mode()  # to 3D
    viewer._toggle_mode()  # back to 2D

    assert viewer.get_orientation() == "Y"
    assert viewer.get_slice() == 3
    assert viewer.project_selector.currentText() == "Project +"


def test_handle_projection_change_is_noop_in_3d(viewer, small_volume):
    """In 3D, ``handle_projection_change`` must not attach clipping planes."""
    import vtk as _vtk

    viewer.swap_volume(small_volume)

    # Add a scene actor so the projection callback has something to act on.
    sphere = _vtk.vtkSphereSource()
    sphere.Update()
    poly_mapper = _vtk.vtkPolyDataMapper()
    poly_mapper.SetInputConnection(sphere.GetOutputPort())
    scene_actor = _vtk.vtkActor()
    scene_actor.SetMapper(poly_mapper)
    viewer.renderer.AddActor(scene_actor)

    viewer._toggle_mode()  # to 3D
    viewer.handle_projection_change("Project +")

    planes = poly_mapper.GetClippingPlanes()
    n_planes = 0 if planes is None else planes.GetNumberOfItems()
    assert n_planes == 0
