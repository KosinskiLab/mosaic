import warnings
from pathlib import Path
from typing import Tuple
from subprocess import run
from os import makedirs
from os.path import splitext, join, basename

import numpy as np

# Hopefully stable download links will be available at some point
MODEL_PATHS = {
    "": "",
    # "MemBrain_seg_v9": "/path/to/model_a.ckpt",
    # "MemBrain_seg_v10": "/home/vmaurer/Documents/segmentation/MemBrain_seg_v10_alpha.ckpt",
}

MEMBRAIN_SETTINGS = {
    "title": "Membrain Settings",
    "settings": [
        {
            "type": "PathSelector",
            "label": "Model",
            "parameter": "model_path",
            "choices": MODEL_PATHS,
            "default": None,
            "description": "Path to pre-trained model ckpt file.",
        },
        {
            "type": "number",
            "label": "Window Size",
            "parameter": "window_size",
            "default": 160,
            "min": 32,
            "max": 512,
            "description": "Size used for inference (smaller values use less GPU but give worse results)",
        },
        {
            "type": "text",
            "label": "Input Sampling",
            "parameter": "input_sampling_rate",
            "default": -1.0,
            "min": 0.1,
            "description": "Pixel size of your tomogram.",
            "notes": "Defaults to the pixel size specified in the header.",
        },
        {
            "type": "text",
            "label": "Output Sampling",
            "parameter": "output_sampling_rate",
            "default": -1.0,
            "min": 0.1,
            "description": "Target pixel size for internal rescaling",
            "notes": "Non default values triggers scaling from input to output scaling.",
        },
        {
            "type": "boolean",
            "label": "Clustering",
            "parameter": "clustering",
            "default": True,
            "description": "Compute connected components of the segmentation",
        },
        {
            "type": "boolean",
            "label": "Augmentation",
            "parameter": "test_time_augmentation",
            "default": True,
            "description": "Use 8-fold test time augmentation for better results but slower runtime",
        },
    ],
}


def _stem(path: str) -> str:
    return splitext(basename(path))[0]


def run_membrainseg(
    tomogram_path: str,
    model_path: str,
    out_folder: str = None,
    window_size: int = 160,
    clustering: bool = True,
    input_sampling_rate: Tuple[float] = -1.0,
    output_sampling_rate: Tuple[float] = -1.0,
    test_time_augmentation: bool = True,
):
    from ..formats.parser import load_density

    warnings.warn(
        "Running MemBrain - Corresponding Citation: "
        "[1] Lamm, L. et al. (2024) bioRxiv, doi.org/10.1101/2024.01.05.574336."
    )
    if out_folder is None:
        out_folder = str(Path.home().joinpath("mosaic/segmentations/membrain"))

    makedirs(out_folder, exist_ok=True)

    cmd = [
        "membrain",
        "segment",
        "--tomogram-path",
        tomogram_path,
        "--out-folder",
        out_folder,
        "--ckpt-path",
        model_path,
        "--sliding-window-size",
        window_size,
    ]
    if test_time_augmentation:
        cmd.append("--test-time-augmentation")
    else:
        cmd.append("--no-test-time-augmentation")

    if clustering:
        cmd.append("--store-connected-components")
    else:
        cmd.append("--no-store-connected-components")

    input_sampling_rate = np.max(input_sampling_rate)
    output_sampling_rate = np.max(output_sampling_rate)

    if output_sampling_rate > 0:
        cmd.extend(["--out-pixel-size", f"{output_sampling_rate}", "--rescale-patches"])

        if input_sampling_rate < 0:
            input_sampling_rate = np.max(
                load_density(tomogram_path, use_memmap=True).sampling_rate
            )
            print(f"Setting samping rate to {input_sampling_rate}.")

    if input_sampling_rate > 0:
        cmd.extend(["--in-pixel-size", f"{input_sampling_rate}"])

    ret = run([str(x) for x in cmd])
    out_path = join(
        out_folder, f"{_stem(tomogram_path)}_{_stem(model_path)}.ckpt_segmented.mrc"
    )

    if ret.stderr:
        print(ret.stdout)
        print(ret.stderr)
        out_path = None

    return out_path
