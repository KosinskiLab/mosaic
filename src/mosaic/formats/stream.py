"""
VTK image source that streams slices from a remote OME-Zarr store.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from collections import OrderedDict

import vtk
import numpy as np
from vtkmodules.util import numpy_support
from vtkmodules.util.vtkAlgorithm import VTKPythonAlgorithmBase


class ZarrPyramid:
    """
    Cache-backed multi-level zarr image pyramid.

    Stateless with respect to "current level" — the caller specifies
    which level to read.  On cache miss, falls back to the best
    available coarser data in cache, upsampled to the requested grid.

    Parameters
    ----------
    levels : list of dict
        Each dict has ``array`` (zarr-like), ``shape`` (Z, Y, X),
        and ``spacing`` (sz, sy, sx).  Ordered finest (0) to coarsest.
    cache_bytes : int
        Maximum decoded chunk cache size in bytes.
    """

    def __init__(self, levels, cache_bytes=512 * 1024**2):
        self._levels = list(levels)
        self._cache_bytes = cache_bytes

        self._cache = OrderedDict()
        self._cache_used = 0
        self._pending = set()
        self._on_chunk_ready = None

    @property
    def num_levels(self):
        return len(self._levels)

    def level_shape(self, n):
        return tuple(self._levels[n]["shape"])

    def level_spacing(self, n):
        return tuple(float(s) for s in self._levels[n]["spacing"])

    def level_spacings(self):
        return [self.level_spacing(i) for i in range(self.num_levels)]

    def read_region(self, level, x0, x1, y0, y1, z0, z1):
        """
        Return a float32 ZYX array for the requested extent at *level*.

        Chunks cached at *level* are used directly.  Missing chunks are
        submitted to the IO pool (if ``on_chunk_ready`` is set) or fetched
        synchronously.  Gaps are filled from the best coarser data in cache.
        """
        shape = (z1 - z0 + 1, y1 - y0 + 1, x1 - x0 + 1)
        result = np.zeros(shape, dtype=np.float32)

        missing = []
        for ck in self._overlapping_chunks(level, x0, x1, y0, y1, z0, z1):
            cache_key = (level, *ck)

            if cache_key not in self._cache:
                if self._on_chunk_ready is not None and cache_key not in self._pending:
                    from mosaic.parallel import submit_io_task

                    missing.append(ck)
                    self._pending.add(cache_key)

                    submit_io_task(
                        "Fetch zarr chunk",
                        self._fetch_chunk,
                        self._on_chunk_ready,
                        level,
                        ck,
                    )
                    continue
                else:
                    self._fetch_chunk(level, ck)

            self._cache.move_to_end(cache_key)
            self._copy_chunk(level, cache_key, ck, result, x0, y0, z0)

        if missing:
            self._fill_fallback(level, result, x0, x1, y0, y1, z0, z1)
        return result

    def _fill_fallback(self, level, result, x0, x1, y0, y1, z0, z1):
        """Fill zero regions from any overlapping cached chunk at another level."""
        cur_sp = self.level_spacing(level)
        phys_z = (z0 * cur_sp[0], (z1 + 1) * cur_sp[0])
        phys_y = (y0 * cur_sp[1], (y1 + 1) * cur_sp[1])
        phys_x = (x0 * cur_sp[2], (x1 + 1) * cur_sp[2])

        entries = sorted(self._cache.items(), key=lambda item: item[0][0])
        for (cl, *ck_idx), chunk_data in entries:
            if cl == level:
                continue

            fb_sp = self.level_spacing(cl)
            zs, ys, xs = self._chunk_slices(cl, *ck_idx)
            cz = (zs.start * fb_sp[0], zs.stop * fb_sp[0])
            cy = (ys.start * fb_sp[1], ys.stop * fb_sp[1])
            cx = (xs.start * fb_sp[2], xs.stop * fb_sp[2])

            if cz[1] <= phys_z[0] or cz[0] >= phys_z[1]:
                continue
            if cy[1] <= phys_y[0] or cy[0] >= phys_y[1]:
                continue
            if cx[1] <= phys_x[0] or cx[0] >= phys_x[1]:
                continue

            # Map chunk's physical overlap back to result voxel coordinates
            oz0 = max(0, int((cz[0] - phys_z[0]) / cur_sp[0]))
            oz1 = min(result.shape[0], int(np.ceil((cz[1] - phys_z[0]) / cur_sp[0])))
            oy0 = max(0, int((cy[0] - phys_y[0]) / cur_sp[1]))
            oy1 = min(result.shape[1], int(np.ceil((cy[1] - phys_y[0]) / cur_sp[1])))
            ox0 = max(0, int((cx[0] - phys_x[0]) / cur_sp[2]))
            ox1 = min(result.shape[2], int(np.ceil((cx[1] - phys_x[0]) / cur_sp[2])))

            target = result[oz0:oz1, oy0:oy1, ox0:ox1]
            if not np.any(target == 0):
                continue

            # Map overlap to source chunk local coordinates
            sz0 = max(0, int((phys_z[0] - cz[0]) / fb_sp[0]))
            sz1 = sz0 + int(np.ceil((oz1 - oz0) * cur_sp[0] / fb_sp[0]))
            sy0 = max(0, int((phys_y[0] - cy[0]) / fb_sp[1]))
            sy1 = sy0 + int(np.ceil((oy1 - oy0) * cur_sp[1] / fb_sp[1]))
            sx0 = max(0, int((phys_x[0] - cx[0]) / fb_sp[2]))
            sx1 = sx0 + int(np.ceil((ox1 - ox0) * cur_sp[2] / fb_sp[2]))

            sz1 = min(sz1, chunk_data.shape[0])
            sy1 = min(sy1, chunk_data.shape[1])
            sx1 = min(sx1, chunk_data.shape[2])

            source = chunk_data[sz0:sz1, sy0:sy1, sx0:sx1]
            self._upsample_into(source, target)

    @staticmethod
    def _upsample_into(source, target):
        """Upsample *source* into zero regions of *target*."""
        if source.shape == target.shape:
            mask = target == 0
            target[mask] = source[mask]
            return None

        from scipy.ndimage import zoom

        factors = tuple(t / s for t, s in zip(target.shape, source.shape))
        upsampled = zoom(source, factors, order=1).astype(np.float32)
        mask = target == 0
        target[mask] = upsampled[mask]

    def _chunks_for(self, level):
        arr = self._levels[level]["array"]
        chunks = getattr(arr, "chunks", None)
        if chunks is None:
            return tuple(self._levels[level]["shape"])
        return tuple(int(c) for c in chunks)

    def _overlapping_chunks(self, level, x0, x1, y0, y1, z0, z1):
        cz, cy, cx = self._chunks_for(level)
        for iz in range(z0 // cz, z1 // cz + 1):
            for iy in range(y0 // cy, y1 // cy + 1):
                for ix in range(x0 // cx, x1 // cx + 1):
                    yield (iz, iy, ix)

    def _chunk_slices(self, level, iz, iy, ix):
        cz, cy, cx = self._chunks_for(level)
        sz, sy, sx = self._levels[level]["shape"]
        return (
            slice(iz * cz, min((iz + 1) * cz, sz)),
            slice(iy * cy, min((iy + 1) * cy, sy)),
            slice(ix * cx, min((ix + 1) * cx, sx)),
        )

    def _copy_chunk(self, level, cache_key, chunk_idx, result, x0, y0, z0):
        chunk_data = self._cache[cache_key]
        zs, ys, xs = self._chunk_slices(level, *chunk_idx)

        rz = slice(max(zs.start, z0) - z0, min(zs.stop, z0 + result.shape[0]) - z0)
        ry = slice(max(ys.start, y0) - y0, min(ys.stop, y0 + result.shape[1]) - y0)
        rx = slice(max(xs.start, x0) - x0, min(xs.stop, x0 + result.shape[2]) - x0)

        sz = slice(
            max(zs.start, z0) - zs.start, min(zs.stop, z0 + result.shape[0]) - zs.start
        )
        sy = slice(
            max(ys.start, y0) - ys.start, min(ys.stop, y0 + result.shape[1]) - ys.start
        )
        sx = slice(
            max(xs.start, x0) - xs.start, min(xs.stop, x0 + result.shape[2]) - xs.start
        )

        result[rz, ry, rx] = chunk_data[sz, sy, sx]

    def _put_cache(self, key, data):
        self._cache[key] = data
        self._cache_used += data.nbytes
        while self._cache_used > self._cache_bytes and self._cache:
            _, evicted = self._cache.popitem(last=False)
            self._cache_used -= evicted.nbytes

    def _fetch_chunk(self, level, chunk_key):
        cache_key = (level, *chunk_key)
        try:
            zs, ys, xs = self._chunk_slices(level, *chunk_key)
            arr = self._levels[level]["array"]
            slab = arr[zs, ys, xs]
            self._put_cache(cache_key, np.ascontiguousarray(slab, dtype=np.float32))
        except Exception:
            pass
        finally:
            # Its probably best to just retry
            self._pending.discard(cache_key)


class ZarrImageSource(VTKPythonAlgorithmBase):
    """
    VTK pipeline source that serves image data from a :class:`ZarrPyramid`.
    Owns the concept of "current level" for VTK extent/spacing reporting.

    Parameters
    ----------
    pyramid : ZarrPyramid
        The data backend.
    initial_level : int
        Pyramid level to start at.
    """

    def __init__(self, pyramid, initial_level=-1):
        super().__init__(
            nInputPorts=0,
            nOutputPorts=1,
            outputType="vtkImageData",
        )
        self.pyramid = pyramid
        self._level = initial_level % pyramid.num_levels

    @property
    def level(self):
        return self._level

    @property
    def num_levels(self):
        return self.pyramid.num_levels

    @property
    def shape(self):
        return self.pyramid.level_shape(self._level)

    @property
    def spacing(self):
        return self.pyramid.level_spacing(self._level)

    @property
    def level_spacings(self):
        return self.pyramid.level_spacings()

    def set_level(self, n):
        n = max(0, min(n, self.num_levels - 1))
        if n != self._level:
            self._level = n

    def set_on_chunk_ready(self, callback):
        self.pyramid._on_chunk_ready = callback

    def RequestInformation(self, request, inInfo, outInfo):
        info = outInfo.GetInformationObject(0)
        z, y, x = self.shape
        info.Set(
            vtk.vtkStreamingDemandDrivenPipeline.WHOLE_EXTENT(),
            0,
            x - 1,
            0,
            y - 1,
            0,
            z - 1,
        )
        info.Set(vtk.vtkDataObject.SPACING(), *self.spacing)
        info.Set(vtk.vtkDataObject.ORIGIN(), 0.0, 0.0, 0.0)
        return 1

    def RequestData(self, request, inInfo, outInfo):
        info = outInfo.GetInformationObject(0)
        output = vtk.vtkImageData.GetData(outInfo)

        ue = info.Get(vtk.vtkStreamingDemandDrivenPipeline.UPDATE_EXTENT())
        x0, x1, y0, y1, z0, z1 = ue

        output.SetExtent(ue)
        output.SetSpacing(*self.spacing)
        output.SetOrigin(0.0, 0.0, 0.0)

        result = self.pyramid.read_region(self._level, x0, x1, y0, y1, z0, z1)

        flat = result.ravel(order="F")
        vtk_arr = numpy_support.numpy_to_vtk(flat, deep=True, array_type=vtk.VTK_FLOAT)
        output.GetPointData().SetScalars(vtk_arr)
        return 1


def resolve_omezarr(url):
    """
    Open a remote OME-Zarr store and return all pyramid levels with metadata.

    Parameters
    ----------
    url : str
        S3 (``s3://...``) or HTTPS URL to an OME-Zarr directory.

    Returns
    -------
    levels : list of dict
        Each dict has ``array``, ``shape``, ``spacing``, ``path``.
    info : dict
        Metadata: ``levels`` (without ``array`` key).
    """
    import zarr

    if url.startswith("s3://"):
        import s3fs

        fs = s3fs.S3FileSystem(anon=True)
        store = s3fs.S3Map(root=url.replace("s3://", ""), s3=fs)
    else:
        import fsspec

        store = fsspec.get_mapper(url)

    store = zarr.LRUStoreCache(store, max_size=2 * 1024**3)

    root = zarr.open(store, mode="r")
    multiscales = root.attrs.get("multiscales", [{}])[0]
    datasets = multiscales.get("datasets", [])

    levels = []
    for ds in datasets:
        path = ds["path"]
        arr = root[path]
        spacing = (1.0, 1.0, 1.0)
        for t in ds.get("coordinateTransformations", []):
            if t.get("type") == "scale":
                spacing = tuple(t["scale"])
                break
        levels.append(
            {
                "path": path,
                "shape": arr.shape,
                "spacing": spacing,
                "array": arr,
            }
        )

    if not levels:
        for key in sorted(root.keys()):
            arr = root[key]
            if hasattr(arr, "shape"):
                levels.append(
                    {
                        "path": key,
                        "shape": arr.shape,
                        "spacing": (1.0, 1.0, 1.0),
                        "array": arr,
                    }
                )

    if not levels:
        raise ValueError(f"No arrays found in Zarr store: {url}")

    info = {
        "levels": [
            {"path": lvl["path"], "shape": lvl["shape"], "spacing": lvl["spacing"]}
            for lvl in levels
        ],
    }

    return levels, info


def open_omezarr(url):
    """
    Open a remote OME-Zarr store and return a VTK streaming source.

    Parameters
    ----------
    url : str
        S3 (``s3://...``) or HTTPS URL to an OME-Zarr directory.

    Returns
    -------
    source : ZarrImageSource
    info : dict
    """
    levels, info = resolve_omezarr(url)
    pyramid = ZarrPyramid(levels)
    source = ZarrImageSource(pyramid)
    return source, info


def pick_level(spacings, world_per_pixel):
    """
    Choose the coarsest pyramid level that is still sharp at the given zoom.

    Parameters
    ----------
    spacings : list of tuple
        ``(sx, sy, sz)`` for each pyramid level, ordered finest to coarsest.
    world_per_pixel : float
        World-space distance covered by one screen pixel.

    Returns
    -------
    int
        Index of the best level.
    """
    best = 0
    for i, sp in enumerate(spacings):
        if max(sp) <= world_per_pixel:
            best = i
    return best
