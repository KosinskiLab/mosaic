MODEL_PATHS = {
    "MemBrain_seg_v9": "/path/to/model_a.ckpt",
    "MemBrain_seg_v9b": "/path/to/model_b.ckpt",
    "MemBrain_seg_v10": "/path/to/model_b.ckpt",
}

MEMBRAIN_SETTINGS = {
    "title": "Segmentation Settings",
    "settings": [
        {
            "type": "MappedComboBox",
            "label": "Model",
            "mapping": MODEL_PATHS,
            "default": "Model A",
            "description": "Pre-trained model checkpoint to be used",
        },
        {
            "type": "number",
            "label": "Window Size",
            "default": 160,
            "min": 32,
            "max": 512,
            "description": "Size used for inference (smaller values use less GPU but give worse results)",
        },
        {
            "type": "float",
            "label": "Input Sampling",
            "default": -1.0,
            "min": 0.1,
            "max": 100.0,
            "step": 0.1,
            "description": "Pixel size of your tomogram.",
            "notes": "Defaults to the pixel size specified in the header.",
        },
        {
            "type": "float",
            "label": "Output Sampling",
            "default": 12.0,
            "min": 0.1,
            "max": 100.0,
            "step": 0.1,
            "description": "Target pixel size for internal rescaling",
        },
        {
            "type": "float",
            "label": "Score Threshold",
            "default": 0.0,
            "min": -1.0,
            "max": 1.0,
            "step": 0.1,
            "description": "Threshold for membrane scoremap to adjust segmented membranes",
        },
        {
            "type": "boolean",
            "label": "Rescaling",
            "default": False,
            "description": "Enable on-the-fly patch rescaling during inference",
        },
        {
            "type": "boolean",
            "label": "Clustering",
            "default": True,
            "description": "Compute connected components of the segmentation",
        },
        {
            "type": "boolean",
            "label": "Augmentation",
            "default": True,
            "description": "Use 8-fold test time augmentation for better results but slower runtime",
        },
    ],
}
