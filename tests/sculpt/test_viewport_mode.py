from unittest.mock import MagicMock, patch

import vtk

from mosaic.sculpt.mode import SculptMode
from mosaic.viewport import ViewportInteractor
from mosaic.widgets.status_indicator import ViewerModes


def test_set_mode_sculpt_constructs_mode_and_activates():
    """set_mode(SCULPT) builds a SculptMode with the cached controller and HUD, then activates it."""
    vm = ViewportInteractor.__new__(ViewportInteractor)
    vm._interaction_mode = "view"
    vm._active_mode = None
    hud = MagicMock()
    vm._sculpt_hud = hud
    vm._sculpt_controller = None
    vm.vtk_widget = MagicMock()
    vm.vtk_widget.GetRenderWindow().GetInteractor.return_value = None
    vm.models_pane = MagicMock()
    vm.panes = [MagicMock(), vm.models_pane]

    with patch("mosaic.sculpt.mode.SculptMode") as MockMode:
        instance = MockMode.return_value
        vm.set_mode(ViewerModes.SCULPT)

    hud.set_tool.assert_called_with("view")
    MockMode.assert_called_once()
    instance.activate.assert_called_once()
    assert vm._interaction_mode == "sculpt"
    assert vm._active_mode is instance


def test_set_mode_viewing_tears_down_active_mode():
    """set_mode(VIEWING) calls deactivate on any prior mode object."""
    vm = ViewportInteractor.__new__(ViewportInteractor)
    vm._interaction_mode = "sculpt"
    prior = MagicMock()
    vm._active_mode = prior
    vm.vtk_widget = MagicMock()
    interactor = MagicMock()
    vm.vtk_widget.GetRenderWindow().GetInteractor.return_value = interactor
    interactor.GetInteractorStyle.return_value = MagicMock(spec=[])  # no cleanup attr
    vm.panes = [MagicMock(), MagicMock()]

    vm.set_mode(ViewerModes.VIEWING)

    prior.deactivate.assert_called_once()
    assert vm._active_mode is None
    assert vm._interaction_mode is None


def test_sculpt_mode_set_tool_syncs_hud_controller_cursor():
    """SculptMode.set_tool is the single verb: HUD + controller + cursor."""
    mode = SculptMode.__new__(SculptMode)
    mode._vtk_widget = MagicMock()
    interactor = MagicMock()
    mode._vtk_widget.GetRenderWindow().GetInteractor.return_value = interactor

    sculpt_style = MagicMock()
    camera_style = vtk.vtkInteractorStyleTrackballCamera()
    mode.style = sculpt_style
    mode.camera_style = camera_style

    hud = MagicMock()
    mode._hud = hud

    controller = MagicMock()
    controller.session = MagicMock()
    mode.controller = controller

    interactor.GetInteractorStyle.return_value = sculpt_style
    mode.set_tool("view")
    hud.set_tool.assert_called_with("view")
    controller.set_tool.assert_called_with("view")
    interactor.SetInteractorStyle.assert_called_with(camera_style)
    controller.set_brush_overlay_visible.assert_called_with(False)

    hud.set_tool.reset_mock()
    controller.set_tool.reset_mock()
    controller.set_brush_overlay_visible.reset_mock()
    interactor.GetInteractorStyle.return_value = camera_style
    interactor.SetInteractorStyle.reset_mock()

    mode.set_tool("grab")
    hud.set_tool.assert_called_with("grab")
    controller.set_tool.assert_called_with("grab")
    interactor.SetInteractorStyle.assert_called_with(sculpt_style)
    controller.set_brush_overlay_visible.assert_called_with(True)


def test_hud_radius_change_routes_through_set_radius():
    """HUD slider edits must go through controller.set_radius so the chosen
    radius is marked user-set and survives the next hover-rebind."""
    mode = SculptMode.__new__(SculptMode)
    controller = MagicMock()
    mode.controller = controller

    mode._on_hud_radius_changed(50.0)

    controller.set_radius.assert_called_once_with(50.0)


def test_sculpt_mode_set_tool_forwards_to_controller_without_session():
    """controller.set_tool runs even without a session so the overlay tint updates."""
    mode = SculptMode.__new__(SculptMode)
    mode._vtk_widget = MagicMock()
    mode._vtk_widget.GetRenderWindow().GetInteractor.return_value = None
    mode.style = None
    mode.camera_style = None

    hud = MagicMock()
    mode._hud = hud

    controller = MagicMock()
    controller.session = None
    mode.controller = controller

    mode.set_tool("grab")
    hud.set_tool.assert_called_with("grab")
    controller.set_tool.assert_called_with("grab")
