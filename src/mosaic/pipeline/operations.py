"""
Operation definitions and categories for pipeline builder.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from mosaic.tabs.segmentation import (
    CLUSTER_SETTINGS,
    DOWNSAMPLE_SETTINGS,
    SKELETONIZE_SETTINGS,
)
from mosaic.tabs.model import (
    MESH_SETTINGS,
    REMESH_SETTINGS,
    SMOOTH_SETTINGS,
    SAMPLE_SETTINGS,
)


OPERATION_CATEGORIES = {
    "input": {
        "title": "Input",
        "color": "#7c3aed",
        "operations": {
            "Import Files": {
                "id": "import_batch",
                "description": "Import multiple files for processing",
                "icon": "mdi6.file-import",
                "has_output": True,
                "input_type": None,
                "output_type": "any",
            },
        },
    },
    "preprocessing": {
        "title": "Preprocessing",
        "color": "#2563eb",
        "operations": {
            "Clustering": {
                "id": "cluster",
                "description": "Group points by spatial proximity",
                "icon": "mdi.sitemap",
                "has_output": True,
                "settings": CLUSTER_SETTINGS,
                "input_type": "point",
                "output_type": "point",
            },
            "Downsampling": {
                "id": "downsample",
                "description": "Reduce point density uniformly",
                "icon": "mdi.focus-field-horizontal",
                "has_output": True,
                "settings": DOWNSAMPLE_SETTINGS,
                "input_type": "point",
                "output_type": "point",
            },
            "Skeletonization": {
                "id": "skeletonize",
                "description": "Extract medial axis structure",
                "icon": "mdi.dots-horizontal",
                "has_output": True,
                "settings": SKELETONIZE_SETTINGS,
                "input_type": "point",
                "output_type": "point",
            },
            "Cluster Selection": {
                "id": "cluster_select",
                "description": "Filter by cluster size",
                "icon": "mdi.chart-histogram",
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
                            "min": 0.0,
                            "default": 0.0,
                        },
                        {
                            "label": "Upper Threshold",
                            "parameter": "upper_threshold",
                            "type": "float",
                            "min": 0.0,
                            "default": 0.0,
                        },
                    ],
                },
            },
        },
    },
    "parametrization": {
        "title": "Parametrization",
        "color": "#059669",
        "operations": {
            "Mesh": {
                "id": "fit",
                "description": "Create surface mesh",
                "icon": "mdi.triangle-outline",
                "has_output": True,
                "settings": MESH_SETTINGS,
                "input_type": "point",
                "output_type": "model",
            },
            "Remesh": {
                "id": "remesh",
                "description": "Optimize mesh connectivity",
                "icon": "mdi.repeat",
                "has_output": True,
                "settings": REMESH_SETTINGS,
                "input_type": "model",
                "output_type": "model",
            },
            "Smoothing": {
                "id": "smooth",
                "description": "Smooth mesh surface",
                "icon": "mdi.blur",
                "has_output": True,
                "settings": SMOOTH_SETTINGS,
                "input_type": "model",
                "output_type": "model",
            },
            "Sample": {
                "id": "sample",
                "description": "Sample from parametrization",
                "icon": "mdi.chart-scatter-plot",
                "has_output": True,
                "settings": SAMPLE_SETTINGS,
                "input_type": "model",
                "output_type": "point",
            },
        },
    },
    "export": {
        "title": "Export",
        "color": "#ea580c",
        "operations": {
            "Export Data": {
                "id": "export_data",
                "description": "Save data from previous step",
                "icon": "mdi6.folder-download",
                "has_output": False,
                "input_type": "any",
                "output_type": None,
                "settings": {
                    "title": "Export Data",
                    "settings": [
                        {
                            "label": "Method",
                            "type": "select",
                            "options": ["Point Cloud", "Mesh", "Volume"],
                            "default": "Point Cloud",
                        },
                        {
                            "label": "Output Directory",
                            "parameter": "output_dir",
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
                                "label": "RELION 5 Transform",
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
                "icon": "mdi6.content-save",
                "has_output": False,
                "input_type": None,
                "output_type": None,
                "settings": {
                    "title": "Save Session",
                    "settings": [
                        {
                            "label": "Output Directory",
                            "parameter": "output_dir",
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
                "method": "star",
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
