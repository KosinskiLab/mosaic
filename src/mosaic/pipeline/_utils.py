"""
Utility functions for pipeline module.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from os.path import basename
from re import split as re_split


def strip_filepath(path: str) -> str:
    """
    Extract base filename without extension.

    Parameters
    ----------
    path : str
        Full file path

    Returns
    -------
    str
        Filename without extension
    """
    return basename(path).split(".")[0]


def natural_sort_key(path):
    """
    Natural sorting key for filenames with numbers.

    Sorts files like: file1.txt, file2.txt, file10.txt
    instead of: file1.txt, file10.txt, file2.txt

    Parameters
    ----------
    path : str
        File path

    Returns
    -------
    list
        Sort key with integers properly ordered
    """
    filename = basename(path)
    parts = re_split(r"(\d+)", filename)
    return [int(part) if part.isdigit() else part.lower() for part in parts]
