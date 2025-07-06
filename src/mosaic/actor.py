"""
VTK actor factory to control rendering settings.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import vtk

from .settings import Settings


class ActorFactory:
    """Singleton factory for creating VTK actors with different quality levels."""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ActorFactory, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.update_from_settings()
            ActorFactory._initialized = True

    def update_from_settings(self):
        self.quality_kwargs = Settings.vtk.get_settings()
        self.quality = self.quality_kwargs.pop("quality", None)

    def is_synced(self) -> bool:
        """Check whether ActorFactory settings are synced with appsettings"""

        quality_kwargs = Settings.vtk.get_settings()
        quality = quality_kwargs.pop("quality", None)

        ret = self.quality == quality
        ret = ret and self.quality_kwargs == quality_kwargs
        return ret

    def create_actor(self) -> vtk.vtkActor:
        """Create an actor based on current quality settings.

        Returns:
            Configured VTK actor
        """
        actor = vtk.vtkActor()
        if self.quality == "lod":
            actor = self._create_lod_actor()
        elif self.quality == "lod_quadric":
            actor = self._create_quadric_lod_actor()
        return actor

    def _create_lod_actor(self) -> vtk.vtkLODActor:
        """Create a Level-of-Detail actor."""
        actor = vtk.vtkLODActor()

        lod_points = int(self.quality_kwargs.get("lod_points", 5e6))
        lod_points_size = int(self.quality_kwargs.get("lod_points_size", 3))

        actor.SetNumberOfCloudPoints(lod_points)
        actor.GetProperty().SetPointSize(lod_points_size)

        # actor = vtk.vtkLODActor()
        # actor.SetNumberOfCloudPoints(int(lod_points))
        # actor.GetProperty().SetPointSize(lod_points_size)

        # medium_filter = vtk.vtkMaskPoints()
        # medium_filter.SetInputData(self._data)
        # medium_filter.RandomModeOff()
        # medium_filter.SetOnRatio(10)
        # medium_filter.SetMaximumNumberOfPoints(5 * lod_points)
        # medium_filter.SetSingleVertexPerCell(True)
        # actor.SetMediumResFilter(medium_filter)

        # low_filter = vtk.vtkOutlineFilter()
        # low_filter.SetInputData(self._data)
        # actor.SetLowResFilter(low_filter)

        return actor

    def _create_quadric_lod_actor(self) -> vtk.vtkQuadricLODActor:
        """Create a Quadric Level-of-Detail actor."""
        return vtk.vtkQuadricLODActor()


QUALITY_PRESETS = {
    "ultra": {"quality": "full"},
    "high": {"quality": "lod", "lod_points": 10e6, "lod_points_size": 2},
    "medium": {
        "quality": "lod",
        "lod_points": 5e6,
        "lod_points_size": 3,
        "use_filters": True,
        "medium_ratio": 5,
    },
    "low": {
        "quality": "lod",
        "lod_points": 1e6,
        "lod_points_size": 4,
        "use_filters": True,
        "medium_ratio": 20,
        "use_outline": True,
    },
    "adaptive": {"quality": "lod_quadric", "max_level": 4, "factor": 2.0},
}


def set_quality_preset(preset_name: str):
    """Set quality using a predefined preset.

    Args:
        preset_name: One of "ultra", "high", "medium", "low", "adaptive"
    """
    if preset_name not in QUALITY_PRESETS:
        raise ValueError(
            f"Unknown preset: {preset_name}. Available: {list(QUALITY_PRESETS.keys())}"
        )

    preset = QUALITY_PRESETS[preset_name]
    quality = preset.pop("quality")
    ActorFactory().set_quality(quality, **preset)


def create_actor():
    return ActorFactory().create_actor()
