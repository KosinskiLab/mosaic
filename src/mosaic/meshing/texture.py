"""
UV texture mapping for mesh visualization.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from functools import lru_cache
from typing import Tuple, Optional

import vtk
import numpy as np
from numpy.typing import NDArray
from vtk.util import numpy_support

from .. import utils

__all__ = ["TextureSampler"]


def compute_uv_coords(
    vertices: NDArray, triangles: NDArray
) -> Tuple[NDArray, NDArray, NDArray]:
    """
    Compute UV coordinates using xatlas.

    Returns
    -------
    vmapping : NDArray
        Mapping from new vertices to original vertices.
    indices : NDArray
        New triangle indices.
    uvs : NDArray
        UV coordinates per vertex.
    """
    try:
        import xatlas
    except ImportError:
        raise ImportError(
            "xatlas is required for mesh texturing. "
            "Install it with: pip install mosaic-gui['texture']"
        ) from None

    vmapping, indices, uvs = xatlas.parametrize(
        np.asarray(vertices, dtype=np.float32),
        np.asarray(triangles, dtype=np.uint32),
    )
    return vmapping, indices, uvs


def _compute_sampling_map(
    texture_size: int,
    tri_verts: NDArray,
    tri_normals: NDArray,
    scaled_uvs: NDArray,
) -> Tuple[NDArray, NDArray]:
    """Precompute per-pixel 3D positions and normals."""
    from skimage.draw import polygon

    # Dense arrays for all texture pixels
    positions = np.full((texture_size, texture_size, 3), np.nan, dtype=np.float32)
    normals = np.full((texture_size, texture_size, 3), np.nan, dtype=np.float32)
    for i in range(len(scaled_uvs)):
        uv = scaled_uvs[i]

        # Skip degenerate triangles
        area = 0.5 * abs(
            (uv[1, 0] - uv[0, 0]) * (uv[2, 1] - uv[0, 1])
            - (uv[2, 0] - uv[0, 0]) * (uv[1, 1] - uv[0, 1])
        )
        if area < 0.5:
            continue

        rr, cc = polygon(uv[:, 1], uv[:, 0], shape=(texture_size, texture_size))
        if len(rr) == 0:
            continue

        bary = _compute_barycentric(np.column_stack([cc, rr]).astype(np.float64), uv)
        if bary is None:
            continue

        pos_3d = (
            bary[:, 0:1] * tri_verts[i, 0]
            + bary[:, 1:2] * tri_verts[i, 1]
            + bary[:, 2:3] * tri_verts[i, 2]
        )

        n = tri_normals[i]
        interp_n = bary[:, 0:1] * n[0] + bary[:, 1:2] * n[1] + bary[:, 2:3] * n[2]
        interp_n /= np.linalg.norm(interp_n, axis=1, keepdims=True) + 1e-10

        positions[rr, cc] = pos_3d.astype(np.float32)
        normals[rr, cc] = interp_n.astype(np.float32)

    valid_mask = ~np.isnan(positions[:, :, 0])
    return positions, normals, np.where(valid_mask)


def _compute_barycentric(points: NDArray, triangle: NDArray) -> Optional[NDArray]:
    """Compute barycentric coordinates for points relative to triangle."""
    v0, v1, v2 = triangle[0], triangle[1], triangle[2]
    d00 = np.dot(v1 - v0, v1 - v0)
    d01 = np.dot(v1 - v0, v2 - v0)
    d11 = np.dot(v2 - v0, v2 - v0)

    denom = d00 * d11 - d01 * d01
    if abs(denom) < 1e-10:
        return None

    d20 = np.sum((points - v0) * (v1 - v0), axis=1)
    d21 = np.sum((points - v0) * (v2 - v0), axis=1)

    v = (d00 * d21 - d01 * d20) / denom
    u = (d11 * d20 - d01 * d21) / denom
    w = 1.0 - u - v

    return np.column_stack([w, u, v])


def _dilate_texture(texture: NDArray, iterations: int = 3) -> NDArray:
    """Dilate texture to fill NaN gaps at UV seams."""
    from scipy.ndimage import binary_dilation, generate_binary_structure

    result = texture.copy()
    struct = generate_binary_structure(2, 2)

    for _ in range(iterations):
        nan_mask = np.isnan(result)
        if not nan_mask.any():
            break

        valid_mask = ~nan_mask
        dilated = binary_dilation(valid_mask, structure=struct)
        fill_mask = dilated & nan_mask

        if not fill_mask.any():
            break

        padded = np.pad(result, 1, mode="constant", constant_values=np.nan)
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                if dy == 0 and dx == 0:
                    continue
                shifted = padded[
                    1 + dy : 1 + dy + texture.shape[0],
                    1 + dx : 1 + dx + texture.shape[1],
                ]
                neighbor_valid = ~np.isnan(shifted) & fill_mask
                result[neighbor_valid] = shifted[neighbor_valid]

    return result


def _wedge_to_vertex_uvs(uvs: NDArray, triangles: NDArray, n_vertices: int) -> NDArray:
    """Convert per-wedge UVs to per-vertex UVs."""
    if uvs.shape[0] == n_vertices:
        return uvs

    per_vertex_uvs = np.zeros((n_vertices, 2), dtype=np.float64)
    counts = np.zeros(n_vertices, dtype=np.int32)

    flat_triangles = triangles.ravel()
    np.add.at(per_vertex_uvs, flat_triangles, uvs[: len(flat_triangles)])
    np.add.at(counts, flat_triangles, 1)

    valid = counts > 0
    per_vertex_uvs[valid] /= counts[valid, np.newaxis]
    return per_vertex_uvs


def _normalize_uvs(uvs: NDArray) -> NDArray:
    """Normalize UVs to [0, 1] range if needed."""
    uv_min, uv_max = uvs.min(axis=0), uvs.max(axis=0)
    if uv_max.max() > 1.0 or uv_min.min() < 0.0:
        return (uvs - uv_min) / (uv_max - uv_min + 1e-10)
    return uvs


@lru_cache(maxsize=4)
def _load_tomogram_cached(file_path: str, interpolation_order: int = 3):
    """Load and cache tomogram data with precomputed spline coefficients."""
    from ..formats.parser import load_density

    density = load_density(file_path, use_memmap=True)

    maxval = density.metadata.get("max", None)
    if maxval is None:
        maxval = density.data.max()

    minval = density.metadata.get("min", None)
    if minval is None:
        minval = density.data.min()

    tomogram = density.data.astype(np.float32)

    if interpolation_order > 1:
        from scipy.ndimage import spline_filter

        tomogram = spline_filter(tomogram, order=interpolation_order, mode="constant")

    return (
        tomogram,
        np.mean(density.sampling_rate),
        (float(minval), float(maxval)),
    )


class TextureSampler:
    """
    Precomputed texture sampler for fast normal offset updates.

    Parameters
    ----------
    geometry : Geometry
        Mesh geometry with a fitted model.
    tomogram_path : str
        Path to the tomogram file.
    texture_size : int, optional
        Texture resolution in pixels. Default is 1024.
    """

    def __init__(
        self,
        geometry,
        tomogram_path: str,
        texture_size: int = 1024,
        interpolation_order: int = 3,
    ):
        fit = geometry.model
        if not hasattr(fit, "mesh"):
            raise ValueError("Geometry must have a fitted mesh model.")

        self.geometry = geometry
        self.texture_size = texture_size
        self.interpolation_order = interpolation_order
        self.tomogram, sampling, self.scalar_range = _load_tomogram_cached(
            tomogram_path, interpolation_order=interpolation_order
        )

        self._cached_offset = None
        self._cached_texture = None

        # xatlas adds new vertices for seams, so we need to update the structure
        vertices = fit.vertices / sampling
        vmapping, triangles, uvs = compute_uv_coords(vertices, fit.triangles)
        triangles = np.asarray(triangles, dtype=np.int32)
        uvs = np.asarray(uvs, dtype=np.float64)

        vertices = vertices[vmapping]
        normals = fit.compute_vertex_normals()[vmapping]
        self._model = fit

        per_vertex_uvs = _wedge_to_vertex_uvs(uvs, triangles, len(vertices))
        per_vertex_uvs = _normalize_uvs(per_vertex_uvs)

        # Precompute per pixel positions
        self._tpositions, self._tnormals, self._valid_indices = _compute_sampling_map(
            texture_size=self.texture_size,
            tri_verts=vertices[triangles],
            tri_normals=normals[triangles],
            scaled_uvs=per_vertex_uvs[triangles] * (texture_size - 1),
        )
        self._tpositions = self._tpositions[self._valid_indices]
        self._tnormals = self._tnormals[self._valid_indices]

        self.geometry.points = vertices * sampling
        self.geometry._set_faces(triangles)
        self.geometry.normals = normals

        self._setup_texture_coords(per_vertex_uvs)
        self._create_vtk_texture()

        self.update(0.0)

    def _setup_texture_coords(self, per_vertex_uvs):
        """Set up texture coordinates on the geometry."""
        tcoords = vtk.vtkFloatArray()
        tcoords.SetNumberOfComponents(2)
        tcoords.SetName("TextureCoordinates")
        for u, v in per_vertex_uvs:
            tcoords.InsertNextTuple2(float(u), float(v))
        self.geometry._data.GetPointData().SetTCoords(tcoords)

    def _create_vtk_texture(self) -> None:
        """Create VTK texture object for rendering."""
        h, w = self.texture_size, self.texture_size
        self._vtk_image = vtk.vtkImageData()
        self._vtk_image.SetDimensions(w, h, 1)
        self._vtk_image.AllocateScalars(vtk.VTK_UNSIGNED_CHAR, 3)

        self._vtk_texture = vtk.vtkTexture()
        self._vtk_texture.SetInputDataObject(self._vtk_image)
        self._vtk_texture.InterpolateOn()
        self._vtk_texture.RepeatOff()
        self._vtk_texture.EdgeClampOn()

        self.geometry.actor.SetTexture(self._vtk_texture)
        self.geometry.actor.GetMapper().ScalarVisibilityOff()

    def update(
        self,
        normal_offset: float = 0.0,
        colormap: Optional[str] = "gray",
        scalar_range: Optional[Tuple[float, float]] = None,
        gamma: float = 1.0,
        quantiles: bool = False,
    ) -> NDArray:
        """
        Resample tomogram at new normal offset.

        Parameters
        ----------
        normal_offset : float
            Offset along surface normals in voxel units.
        colormap : str, optional
            Colormap name. Uses instance colormap if not specified.
        scalar_range : tuple, optional
            (vmin, vmax) for color scaling. Auto-computed if not specified.
        gamma : float, optional
            Gamma correction factor, by default 1.0. Values < 1 brighten
            dark regions, > 1 darken bright regions.
        quantiles : bool, optional
            If True, map values to quantile bins before colormapping.

        Returns
        -------
        NDArray
            The sampled texture values.
        """
        # Defer update if this is just a visualization change
        if normal_offset != self._cached_offset or self._cached_texture is None:
            from scipy.ndimage import map_coordinates

            positions = self._tpositions.copy()
            if normal_offset != 0.0:
                positions += normal_offset * self._tnormals

            values = map_coordinates(
                self.tomogram,
                positions.T,
                order=self.interpolation_order,
                mode="constant",
                cval=np.nan,
                prefilter=False,
            ).astype(np.float32)

            texture = np.full(
                (self.texture_size, self.texture_size), np.nan, dtype=np.float32
            )
            texture[self._valid_indices] = values
            texture = _dilate_texture(texture)
            self._cached_offset = normal_offset
            self._cached_texture = texture
        else:
            texture = self._cached_texture.copy()

        valid_mask = ~np.isnan(texture)

        if quantiles and valid_mask.any():
            valid_vals = texture[valid_mask]
            n_bins = min(valid_vals.size // 10, 100)
            if n_bins > 1:
                bins = np.percentile(valid_vals, np.linspace(0, 100, n_bins + 1))
                texture[valid_mask] = np.digitize(valid_vals, bins) - 1
                scalar_range = (0, n_bins - 1)

        if scalar_range is None:
            vmin = texture[valid_mask].min() if valid_mask.any() else 0
            vmax = texture[valid_mask].max() if valid_mask.any() else 1
        else:
            vmin, vmax = scalar_range

        normalized = np.zeros_like(texture)
        normalized[valid_mask] = np.clip(
            (texture[valid_mask] - vmin) / (vmax - vmin + 1e-10), 0, 1
        )
        if gamma != 1.0:
            normalized[valid_mask] = np.power(normalized[valid_mask], 1.0 / gamma)

        cmap = utils.get_cmap(colormap)
        colored = (cmap(normalized)[:, :, :3] * 255).astype(np.uint8)
        colored[~valid_mask] = 128

        vtk_array = numpy_support.numpy_to_vtk(
            np.ascontiguousarray(colored.reshape(-1, 3)),
            deep=True,
            array_type=vtk.VTK_UNSIGNED_CHAR,
        )

        # We set this again in case the object was deselected
        self.geometry.actor.GetMapper().ScalarVisibilityOff()
        self._vtk_image.GetPointData().SetScalars(vtk_array)
        self._vtk_image.Modified()
        self._vtk_texture.Modified()

        return texture

    def cleanup(self):
        """
        Restore original mesh and remove texture from geometry.
        """
        self.geometry.actor.SetTexture(None)
        self.geometry.actor.GetMapper().ScalarVisibilityOn()
        self.geometry._data.GetPointData().SetTCoords(None)

        self.geometry.points = self._model.vertices
        self.geometry._set_faces(self._model.triangles)
        self.geometry.normals = self._model.compute_vertex_normals()

        self.tomogram = None
        self._cached_texture = None
