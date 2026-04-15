import importlib

_module_map = {
    ".cards": [
        "Card",
        "FlowLayout",
    ],
    ".path_selector": ["PathSelector"],
    ".dialog_footer": ["DialogFooter"],
    ".search_widget": ["SearchWidget"],
    ".sidebar": ["ObjectBrowserSidebar"],
    ".sliders": ["DualHandleSlider", "SliderRow", "HistogramRangeSlider"],
    ".trajectory_player": ["TrajectoryPlayer"],
    ".ribbon": ["RibbonToolBar", "create_button"],
    ".colors": [
        "ColorSwatch",
        "ColorPickerRow",
        "ColorMapSelector",
        "generate_gradient_colors",
    ],
    ".volume_viewer": ["VolumeViewer"],
    ".vtk_widgets": [
        "AxesWidget",
        "BoundingBoxManager",
        "LegendWidget",
        "ScaleBarWidget",
    ],
    ".container_list": [
        "ContainerListWidget",
        "ContainerTreeWidget",
        "GroupTreeWidgetItem",
        "StyledListWidgetItem",
        "StyledTreeWidgetItem",
    ],
    ".status_indicator": ["StatusIndicator", "CursorModeHandler", "ViewerModes"],
    ".appsettings": ["AppSettingsPanel"],
    ".tabs": ["TabBar", "TabWidget"],
    ".settings": [
        "format_tooltip",
        "create_setting_widget",
        "get_widget_value",
        "set_widget_value",
        "get_layout_widget_value",
    ],
}

_lazy_imports = {}
for module_path, functions in _module_map.items():
    _lazy_imports[module_path.lstrip(".")] = (module_path, "")
    for func_name in functions:
        _lazy_imports[func_name] = (module_path, func_name)


def __getattr__(name):
    module_path, attr_name = _lazy_imports.get(name, ("", ""))

    if not module_path:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    mod = importlib.import_module(module_path, __name__)
    if attr_name:
        mod = getattr(mod, attr_name)

    globals()[name] = mod
    return mod
