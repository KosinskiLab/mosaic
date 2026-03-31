"""
Operation definitions and categories for pipeline builder.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from mosaic.registry import MethodRegistry
from mosaic.stylesheets import Colors
import mosaic.operations  # noqa: F401  # registers geometry operations
from mosaic.tabs.model import SAMPLE_SETTINGS

CLUSTER_SETTINGS = MethodRegistry.settings_dict("cluster")
DOWNSAMPLE_SETTINGS = MethodRegistry.settings_dict("downsample")
SKELETONIZE_SETTINGS = MethodRegistry.settings_dict("skeletonize")
MESH_SETTINGS = MethodRegistry.settings_dict("fit")
REMESH_SETTINGS = MethodRegistry.settings_dict("remesh")
SMOOTH_SETTINGS = MethodRegistry.settings_dict("smooth")

MESH_ANALYSIS_SETTINGS = MethodRegistry.settings_dict("mesh_analysis")


OPERATION_CATEGORIES = {
    "input": {
        "title": "Input",
        "color": Colors.CATEGORY["input"],
        "operations": {
            "Import Files": {
                "id": "import_batch",
                "description": "Import multiple files for processing",
                "icon": "ph.file-arrow-down",
                "has_output": True,
                "input_type": None,
                "output_type": "any",
            },
        },
    },
    "preprocessing": {
        "title": "Preprocessing",
        "color": Colors.CATEGORY["preprocessing"],
        "operations": {
            "Clustering": {
                "id": "cluster",
                "description": "Group points by spatial proximity",
                "icon": "ph.arrows-out-line-horizontal",
                "has_output": True,
                "settings": CLUSTER_SETTINGS,
                "input_type": "point",
                "output_type": "point",
            },
            "Downsampling": {
                "id": "downsample",
                "description": "Reduce point density uniformly",
                "icon": "ph.arrows-in",
                "has_output": True,
                "settings": DOWNSAMPLE_SETTINGS,
                "input_type": "point",
                "output_type": "point",
            },
            "Skeletonization": {
                "id": "skeletonize",
                "description": "Extract medial axis structure",
                "icon": "ph.line-segments",
                "has_output": True,
                "settings": SKELETONIZE_SETTINGS,
                "input_type": "point",
                "output_type": "point",
            },
            "Cluster Selection": {
                "id": "cluster_select",
                "description": "Filter by cluster size",
                "icon": "ph.chart-bar",
                "has_output": False,
                "input_type": "point",
                "output_type": "point",
                "settings": {
                    "title": "Cluster Selection",
                    "settings": [
                        {
                            "label": "Lower Threshold",
                            "parameter": "lower_threshold",
                            "type": "float",
                            "min": -1.0,
                            "default": -1.0,
                            "special_text": "Disabled",
                        },
                        {
                            "label": "Upper Threshold",
                            "parameter": "upper_threshold",
                            "type": "float",
                            "min": -1.0,
                            "default": -1.0,
                            "special_text": "Disabled",
                        },
                    ],
                },
            },
        },
    },
    "parametrization": {
        "title": "Parametrization",
        "color": Colors.CATEGORY["parametrization"],
        "operations": {
            "Mesh": {
                "id": "fit",
                "description": "Create surface mesh",
                "icon": "ph.triangle",
                "has_output": True,
                "settings": MESH_SETTINGS,
                "input_type": "point",
                "output_type": "model",
            },
            "Remesh": {
                "id": "remesh",
                "description": "Optimize mesh connectivity",
                "icon": "ph.arrows-clockwise",
                "has_output": True,
                "settings": REMESH_SETTINGS,
                "input_type": "model",
                "output_type": "model",
            },
            "Smoothing": {
                "id": "smooth",
                "description": "Smooth mesh surface",
                "icon": "ph.drop",
                "has_output": True,
                "settings": SMOOTH_SETTINGS,
                "input_type": "model",
                "output_type": "model",
            },
            "Sample": {
                "id": "sample",
                "description": "Sample from parametrization",
                "icon": "ph.broadcast",
                "has_output": True,
                "settings": SAMPLE_SETTINGS,
                "input_type": "model",
                "output_type": "point",
            },
        },
    },
    "analysis": {
        "title": "Analysis",
        "color": Colors.CATEGORY["analysis"],
        "operations": {
            "Mesh Analysis": {
                "id": "mesh_analysis",
                "description": "Compute mesh properties",
                "icon": "ph.chart-line",
                "has_output": False,
                "input_type": "model",
                "output_type": "model",
                "settings": MESH_ANALYSIS_SETTINGS,
            },
        },
    },
    "export": {
        "title": "Export",
        "color": Colors.CATEGORY["export"],
        "operations": {
            "Export Data": {
                "id": "export_data",
                "description": "Save data from previous step",
                "icon": "ph.download",
                "has_output": False,
                "input_type": "any",
                "output_type": None,
                "settings": {
                    "title": "Export Data",
                    "settings": [
                        {
                            "label": "Method",
                            "parameter": "method",
                            "type": "select",
                            "options": ["Point Cloud", "Mesh", "Volume"],
                            "default": "Point Cloud",
                        },
                        {
                            "label": "Output Directory",
                            "parameter": "output_dir",
                            "default": "mosaic_export",
                            "type": "PathSelector",
                            "file_mode": False,
                            "placeholder": "Select output directory",
                        },
                    ],
                    "method_settings": {
                        "Point Cloud": [
                            {
                                "label": "Format",
                                "parameter": "format",
                                "type": "select",
                                "options": ["star", "xyz", "tsv"],
                                "default": "star",
                            },
                            {
                                "label": "Relion 5",
                                "parameter": "relion_5_format",
                                "type": "boolean",
                                "description": "Apply RELION 5 format coordinate transformation",
                                "default": False,
                            },
                        ],
                        "Mesh": [
                            {
                                "label": "Format",
                                "parameter": "format",
                                "type": "select",
                                "options": ["obj", "stl", "ply"],
                                "default": "obj",
                            },
                        ],
                        "Volume": [
                            {
                                "label": "Format",
                                "parameter": "format",
                                "type": "select",
                                "options": ["mrc", "em", "h5"],
                                "default": "mrc",
                            },
                        ],
                    },
                },
            },
            "Save Session": {
                "id": "save_session",
                "description": "Save entire session",
                "icon": "ph.floppy-disk",
                "has_output": False,
                "input_type": None,
                "output_type": None,
                "settings": {
                    "title": "Save Session",
                    "settings": [
                        {
                            "label": "Output Directory",
                            "parameter": "output_dir",
                            "default": "mosaic_session",
                            "type": "PathSelector",
                            "file_mode": False,
                            "placeholder": "Select output directory",
                        }
                    ],
                },
            },
        },
    },
}

PIPELINE_PRESETS = {
    "Import": [
        {
            "name": "Import Files",
            "category": "input",
            "settings": {},
        },
        {
            "name": "Save Session",
            "category": "export",
            "settings": {
                "output_dir": "mosaic_import",
            },
        },
    ],
    "Cleanup": [
        {
            "name": "Import Files",
            "category": "input",
            "save_output": False,
            "settings": {},
        },
        {
            "name": "Clustering",
            "category": "preprocessing",
            "settings": {
                "method": "Connected Components",
            },
        },
        {
            "name": "Cluster Selection",
            "category": "preprocessing",
            "settings": {
                "lower_threshold": 1000,
            },
        },
        {
            "name": "Save Session",
            "category": "export",
            "settings": {
                "output_dir": "mosaic_cleanup",
            },
        },
    ],
    "Meshing": [
        {
            "name": "Import Files",
            "category": "input",
            "save_output": False,
            "settings": {},
        },
        {
            "name": "Clustering",
            "category": "preprocessing",
            "save_output": False,
            "settings": {
                "method": "Connected Components",
            },
        },
        {
            "name": "Downsampling",
            "category": "preprocessing",
            "visible_output": False,
            "settings": {
                "method": "Radius",
                "voxel_size": 150,
            },
        },
        {
            "name": "Mesh",
            "category": "parametrization",
            "settings": {
                "method": "Poisson",
                "distance": "200",
            },
        },
        {
            "name": "Save Session",
            "category": "export",
            "settings": {
                "output_dir": "mosaic_meshing",
            },
        },
    ],
    "Particle Picking": [
        {
            "name": "Import Files",
            "category": "input",
            "save_output": False,
            "settings": {},
        },
        {
            "name": "Clustering",
            "category": "preprocessing",
            "visible_output": False,
            "settings": {
                "method": "Connected Components",
            },
        },
        {
            "name": "Cluster Selection",
            "category": "preprocessing",
            "settings": {
                "lower_threshold": 2500,
            },
        },
        {
            "name": "Mesh",
            "category": "parametrization",
            "save_output": False,
            "settings": {
                "method": "Flying Edges",
            },
        },
        {
            "name": "Remesh",
            "category": "parametrization",
            "save_output": False,
            "settings": {
                "method": "Decimation",
                "decimation_method": "Reduction Factor",
                "sampling": 10,
                "smooth": True,
            },
        },
        {
            "name": "Smoothing",
            "category": "parametrization",
            "settings": {
                "method": "Taubin",
                "number_of_iterations": 10,
            },
        },
        {
            "name": "Sample",
            "category": "parametrization",
            "settings": {
                "method": "Distance",
                "sampling": 30,
            },
        },
        {
            "name": "Export Data",
            "category": "export",
            "settings": {
                "method": "Point Cloud",
                "format": "star",
                "output_dir": "mosaic_seedpoints",
            },
        },
        {
            "name": "Save Session",
            "category": "export",
            "settings": {
                "output_dir": "mosaic_picking",
            },
        },
    ],
}
