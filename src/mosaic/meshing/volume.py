"""
Tools for sharded meshing of large volumes using marching cubes,
merging of submeshes and simplification using quadratic edge collapse.

This loosely follows the approach taken in igneous (github.com/seung-lab/igneous)
but is focused on simplifying local meshing of large volumes.

Copyright (c) 2024-2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from typing import Tuple, List
from os import listdir, makedirs
from os.path import join, basename
from tempfile import TemporaryDirectory

import numpy as np
import open3d as o3d
from tqdm.contrib.concurrent import process_map

from .utils import merge_meshes, to_open3d

__all__ = [
    "mesh_volume",
    "simplify_mesh",
    "MeshCreator",
    "MeshMerger",
    "MeshSimplifier",
]


def simplify_mesh(mesh, aggressiveness=5.5, decimation_factor=2, lod=1):
    import pyfqmr

    simplifier = pyfqmr.Simplify()
    simplifier.setMesh(np.asarray(mesh.vertices), np.asarray(mesh.triangles))
    simplifier.simplify_mesh(
        target_count=max(int(len(mesh.triangles) / (decimation_factor**lod)), 4),
        aggressiveness=aggressiveness,
        preserve_border=True,
        verbose=False,
    )

    vertices, faces, normals = simplifier.getMesh()
    return to_open3d(vertices, faces)


class MeshCreator:
    def __init__(
        self,
        data_path: str,
        output_dir: str,
        shape: Tuple[int, int, int],
        offset: Tuple[int, int, int],
        **kwargs,
    ):
        """
        Convert labels in specified bounding box into meshes via marching cubes.

        Args:
            data_path: path to volume data
            output_dir: path to write meshes to
            shape: (sx,sy,sz) size of task
            offset: (x,y,z) offset from origin

        Optional kwargs:
            simplification_factor: Try to reduce triangles by this factor
            max_simplification_error: Max distance to move vertices during simplification
            low_padding: Padding to subtract from bbox min
            high_padding: Padding to add to bbox max
            dust_threshold: Skip labels smaller than this
            closed_dataset_edges: Close meshes at dataset boundaries
        """
        self.shape = np.asarray(shape, dtype=int)
        self.offset = np.asarray(offset, dtype=int)
        self.data_path = data_path
        self.output_dir = output_dir

        self.options = {
            "simplification_factor": kwargs.get("simplification_factor", 100),
            "max_simplification_error": kwargs.get("max_simplification_error", None),
            "low_padding": kwargs.get("low_padding", 0),
            "high_padding": kwargs.get("high_padding", 1),
            "dust_threshold": kwargs.get("dust_threshold", None),
            "closed_dataset_edges": kwargs.get("closed_dataset_edges", True),
        }

    def execute(self):
        from zmesh import Mesher
        from ..formats.parser import load_density

        self._volume = load_density(self.data_path, use_memmap=True)
        bounds_min = np.maximum(self.offset.astype(int, copy=True), 0)
        bounds_max = np.minimum(
            np.add(bounds_min, self.shape), self._volume.shape
        ).astype(int)

        data_bounds_min = np.maximum(
            np.subtract(bounds_min, self.options["low_padding"]), 0
        )
        data_bounds_max = np.minimum(
            np.add(bounds_max, self.options["high_padding"]), self._volume.shape
        )

        subset = tuple(
            slice(int(x), int(y)) for x, y in zip(data_bounds_min, data_bounds_max)
        )
        volume = load_density(self.data_path, subset=subset)

        data = volume.data
        if not np.any(data):
            return None

        left_offset = (0, 0, 0)
        if self.options["closed_dataset_edges"]:
            data, left_offset = self._handle_dataset_boundary(
                data, data_bounds_min, data_bounds_max, self._volume.shape
            )

        # Igneus includes dust removal before this step
        mesher = Mesher(volume.sampling_rate)
        mesher.mesh(data)
        data = None

        meshes = {}
        for obj_id in mesher.ids():
            mesh = mesher.get(
                obj_id,
                reduction_factor=self.options["simplification_factor"],
                max_error=self.options["max_simplification_error"],
                voxel_centered=True,
            )
            mesher.erase(obj_id)
            offset = np.subtract(data_bounds_min, left_offset)
            mesh.vertices[:] += offset * volume.sampling_rate
            meshes[obj_id] = mesh

        ret = []
        for k, v in meshes.items():
            bound_str = "-".join([str(x) for x in data_bounds_min.tolist()])
            fname = join(self.output_dir, f"{k}_{bound_str}.obj")
            with open(fname, mode="wb") as ofile:
                ofile.write(v.to_obj())
            ret.append(fname)

        return ret

    def _handle_dataset_boundary(self, data, bounds_min, bounds_max, volume_bounds):
        """Add zero border along dataset boundaries for closed meshes."""
        if (not np.any(bounds_min == 0)) and (not np.any(bounds_max == volume_bounds)):
            return data, (0, 0, 0)

        shape = list(data.shape)
        offset = [0, 0, 0]

        for i in range(3):
            if bounds_min[i] == 0:
                offset[i] += 1
                shape[i] += 1
            if bounds_max[i] == volume_bounds[i]:
                shape[i] += 1

        slices = tuple(slice(o, o + s) for o, s in zip(offset, data.shape))

        padded_data = np.zeros(shape, dtype=data.dtype, order="F")
        padded_data[slices] = data

        for i, o in enumerate(offset):
            if o:
                idx = [slice(None)] * 3
                idx[i] = 0
                padded_data[tuple(idx)] = 0

        return padded_data, tuple(offset)


class MeshMerger:
    def __init__(self, data_path: str, seq_id: str, output_dir: str):
        """
        Merge multiple submesh files into a single combined mesh.

        Args:
            data_path: path to directory containing submesh files
            seq_id: identifier to filter relevant submesh files
            output_dir: path to write merged mesh to
        """
        self.seq_id = seq_id
        self.data_path = data_path
        self.output_dir = output_dir

    def execute(self):
        meshes = [o3d.io.read_triangle_mesh(x) for x in self._get_submeshes()]

        vertices, faces = merge_meshes(
            [mesh.vertices for mesh in meshes], [mesh.triangles for mesh in meshes]
        )
        mesh = to_open3d(vertices, faces)

        opath = join(self.output_dir, f"{self.seq_id}.obj")
        o3d.io.write_triangle_mesh(opath, mesh)
        return opath

    def _get_submeshes(self):
        files = [x for x in listdir(self.data_path) if x.startswith(f"{self.seq_id}_")]
        return [join(self.data_path, x) for x in files]


class MeshSimplifier:
    def __init__(
        self,
        mesh_path,
        output_dir: str,
        decimation_factor: int = 2,
        aggressiveness: float = 5.5,
        lod: int = 1,
    ):
        """
        Simplify mesh by quadratic edge collapse.

        Args:
            mesh_path: path to input mesh file
            output_dir: path to write simplified mesh to
            decimation_factor: factor by which to reduce triangle count
            aggressiveness: controls how aggressively to simplify (higher = more aggressive)
            lod: level of detail, higher values result in more simplification
        """
        self.mesh_path = mesh_path
        self.output_dir = output_dir
        self.decimation_factor = decimation_factor
        self.aggressiveness = aggressiveness
        self.lod = lod

    def execute(self):
        mesh = o3d.io.read_triangle_mesh(self.mesh_path)
        mesh = simplify_mesh(
            mesh,
            decimation_factor=self.decimation_factor,
            aggressiveness=self.aggressiveness,
            lod=self.lod,
        )
        opath = join(self.output_dir, basename(self.mesh_path))
        o3d.io.write_triangle_mesh(opath, mesh)
        return opath


def _execute(task):
    return task.execute()


def _split_volume(shape, box) -> List:
    sx, sy, sz = np.ceil(np.divide(shape, box)).astype(int)
    sxy = sx * sy
    num_tasks = sxy * sz

    ret = []
    for index in range(num_tasks):
        z = index // sxy
        y = (index - (z * sxy)) // sx
        x = index - sx * (y + z * sy)
        ret.append(np.multiply(box, (x, y, z)).astype(int))
    return ret


def mesh_volume(
    volume_path: str,
    output_dir: str = None,
    shape: Tuple[int, int, int] = (448, 448, 448),
    num_workers: int = 8,
    closed_dataset_edges: bool = True,
    max_simplification_error: float = 40,
    simplification_factor: int = 100,
):
    from ..formats.parser import load_density

    if output_dir is None:
        output_dir = TemporaryDirectory(ignore_cleanup_errors=True).name

    partial_meshes = join(output_dir, "partial")
    merged_meshes = join(output_dir, "merged")
    simplified_meshes = join(output_dir, "simplified")
    for dir_name in (partial_meshes, merged_meshes, simplified_meshes):
        makedirs(dir_name, exist_ok=True)

    volume = load_density(volume_path, use_memmap=True)
    if shape is None:
        shape = volume.shape

    tasks = [
        MeshCreator(
            volume_path,
            shape=shape,
            offset=x,
            output_dir=partial_meshes,
            closed_dataset_edges=closed_dataset_edges,
            max_simplification_error=max_simplification_error,
            simplification_factor=simplification_factor,
        )
        for x in _split_volume(volume.shape, shape)
    ]
    _ = process_map(_execute, tasks, max_workers=num_workers)

    seq_ids = set([x.split("_")[0] for x in listdir(partial_meshes)])
    tasks = [
        MeshMerger(partial_meshes, seq_id=x, output_dir=merged_meshes) for x in seq_ids
    ]
    _ = process_map(_execute, tasks, max_workers=num_workers)

    merged_meshes = [join(merged_meshes, f"{x}.obj") for x in seq_ids]
    tasks = [MeshSimplifier(x, output_dir=simplified_meshes) for x in merged_meshes]
    return process_map(_execute, tasks, max_workers=num_workers)
