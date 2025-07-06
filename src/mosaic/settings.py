"""
Centralized settings configuration for Mosaic application.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from dataclasses import dataclass, fields
from typing import Tuple, get_origin, Dict

from qtpy.QtCore import QSettings


class SettingsProperty:
    """Descriptor that automatically syncs with QSettings."""

    def __init__(self, key: str, default, value_type):
        self.key = key
        self.default = default
        self.value_type = value_type

        self._value = None
        self._loaded = False

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self

        if not self._loaded:
            self._load_from_qsettings(obj._qsettings)

        return self._value

    def __set__(self, obj, value):
        self._value = value
        self._loaded = True

        obj._qsettings.setValue(self.key, value)

    def _load_from_qsettings(self, qsettings: QSettings):
        """Load value from QSettings."""
        if not qsettings.contains(self.key):
            self._value = self.default
            self._loaded = True
            return None

        defaults = (bool, int, float, str)
        if self.value_type in defaults:
            self._value = qsettings.value(self.key, type=self.value_type)
        elif get_origin(self.value_type) is tuple:
            stored_value = qsettings.value(self.key, self.default)
            if isinstance(stored_value, (list, tuple)):
                self._value = tuple(stored_value)
            else:
                self._value = self.default
        else:
            self._value = qsettings.value(self.key, self.default)

        self._loaded = True


class SettingsCategory:
    """Base class for settings categories with auto-sync properties."""

    def __init__(self, category: str, dataclass: dataclass):
        self._qsettings = QSettings("Mosaic")
        self._category_name = category
        self._fields = []

        # Dynamically add settings property to this instance
        for field in fields(dataclass):
            prop = SettingsProperty(
                key=f"{category}/{field.name}",
                default=field.default,
                value_type=field.type,
            )
            setattr(self.__class__, field.name, prop)

            self._fields.append(field.name)

    def get_settings(self) -> Dict:
        """Return all settings associated with the class"""
        return {field_name: getattr(self, field_name) for field_name in self._fields}


@dataclass
class RenderingSettings:
    """VTK rendering configuration."""

    background_color: Tuple[float, float, float] = (0.1, 0.1, 0.1)
    background_color_alt: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    use_gradient_background: bool = False
    target_fps: float = 30.0
    enable_fxaa: bool = True
    use_depth_peeling: bool = True
    max_depth_peels: int = 4
    occlusion_ratio: float = 0.0
    multisamples: int = 0
    point_smoothing: bool = False
    line_smoothing: bool = False
    polygon_smoothing: bool = False


@dataclass
class UISettings:
    """User interface configuration."""

    window_size_ratio: Tuple[float, float] = (0.9, 0.9)
    splitter_ratio: float = 0.85
    tab_height: int = 40
    tab_border_color: str = "#6b7280"
    tab_active_color: str = "rgba(99, 102, 241, 1.0)"
    menu_border_color: str = "#6b7280"
    recent_files: Tuple[str, ...] = ()
    max_recent_files: int = 10
    auto_save_session: bool = False
    auto_save_interval: int = 300


@dataclass
class WidgetSettings:
    """Widget visibility and behavior defaults."""

    axes_visible: bool = True
    axes_labels_visible: bool = True
    axes_colored: bool = True
    axes_arrows_visible: bool = True
    scale_bar_visible: bool = False
    legend_visible: bool = False
    legend_orientation: str = "vertical"
    status_indicator_visible: bool = True
    volume_viewer_visible: bool = False
    trajectory_player_visible: bool = False
    auto_hide_widgets_on_fullscreen: bool = True


@dataclass
class WarningSettings:
    """Widget visibility and behavior defaults."""

    suppress_large_file_warning: bool = False


@dataclass
class vtkActorSettings:
    """vtkActor settings."""

    preset: str = "high"
    quality: str = "lod"
    lod_points: int = int(5e6)
    lod_points_size: int = int(3)


class SettingsManager:
    """Manages application settings with automatic persistence."""

    def __init__(self):

        # Category names need to be unique to avoid collisions
        self.rendering = SettingsCategory("rendering", RenderingSettings)
        self.ui = SettingsCategory("ui", UISettings)
        self.widgets = SettingsCategory("widgets", WidgetSettings)
        self.warnings = SettingsCategory("warnings", WarningSettings)
        self.vtk = SettingsCategory("vtk", vtkActorSettings)

    def reset_to_defaults(self, category: str = None):
        """Reset settings to defaults."""

        categories = [category]
        if category is None:
            categories = ["rendering", "ui", "widgets", "vtk"]

        for cat in categories:
            if not hasattr(self, cat):
                continue

            dataclass_map = {
                "rendering": RenderingSettings,
                "ui": UISettings,
                "widgets": WidgetSettings,
            }

            if cat not in dataclass_map:
                continue

            defaults = dataclass_map[cat]()
            category_obj = getattr(self, cat)
            for field in fields(defaults):
                setattr(category_obj, field.name, field.default)


Settings = SettingsManager()

__all__ = ["Settings"]
