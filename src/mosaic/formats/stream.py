"""
VTK image source that streams slices from a remote OME-Zarr store.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import threading
from collections import OrderedDict

import vtk
import numpy as np
from vtkmodules.util import numpy_support
from vtkmodules.util.vtkAlgorithm import VTKPythonAlgorithmBase


class ZarrImageSource(VTKPythonAlgorithmBase):
    """
    VTK image source backed by a Zarr array with async prefetch.

    Parameters
    ----------
    zarr_array : zarr.Array
        Opened Zarr array, shape ``(Z, Y, X)``.
    spacing : tuple of float
        Voxel spacing ``(sx, sy, sz)``.
    on_slice_ready : callable, optional
        Called (from the background thread) when a prefetched slice
        is ready.  The volume viewer connects this to trigger a
        re-render on the main thread.
    cache_slices : int
        Number of slices to keep in the LRU cache.
    """

    def __init__(
        self, zarr_array, spacing=(1.0, 1.0, 1.0), on_slice_ready=None, cache_slices=64
    ):
        super().__init__(
            nInputPorts=0,
            nOutputPorts=1,
            outputType="vtkImageData",
        )
        self._arr = zarr_array
        self._spacing = tuple(float(s) for s in spacing)
        self._shape = zarr_array.shape
        self._on_slice_ready = on_slice_ready

        self._cache = OrderedDict()
        self._cache_max = cache_slices
        self._lock = threading.Lock()
        self._pending = set()

    def RequestInformation(self, request, inInfo, outInfo):
        info = outInfo.GetInformationObject(0)
        z, y, x = self._shape
        info.Set(
            vtk.vtkStreamingDemandDrivenPipeline.WHOLE_EXTENT(),
            0,
            x - 1,
            0,
            y - 1,
            0,
            z - 1,
        )
        info.Set(vtk.vtkDataObject.SPACING(), *self._spacing)
        info.Set(vtk.vtkDataObject.ORIGIN(), 0.0, 0.0, 0.0)
        return 1

    def RequestData(self, request, inInfo, outInfo):
        info = outInfo.GetInformationObject(0)
        output = vtk.vtkImageData.GetData(outInfo)

        ue = info.Get(vtk.vtkStreamingDemandDrivenPipeline.UPDATE_EXTENT())
        x0, x1, y0, y1, z0, z1 = ue
        key = (x0, x1, y0, y1, z0, z1)

        output.SetExtent(ue)
        output.SetSpacing(*self._spacing)
        output.SetOrigin(0.0, 0.0, 0.0)

        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                flat = self._cache[key]
            else:
                flat = None

        if flat is not None:
            vtk_arr = numpy_support.numpy_to_vtk(
                flat, deep=False, array_type=vtk.VTK_FLOAT
            )
            output.GetPointData().SetScalars(vtk_arr)
        else:
            # Cache miss, return zeros for now and fetch in the background
            n = (x1 - x0 + 1) * (y1 - y0 + 1) * (z1 - z0 + 1)
            vtk_arr = numpy_support.numpy_to_vtk(
                np.zeros(n, dtype=np.float32),
                deep=True,
                array_type=vtk.VTK_FLOAT,
            )
            output.GetPointData().SetScalars(vtk_arr)

            # Rerender when slice is ready
            with self._lock:
                if key not in self._pending:
                    self._pending.add(key)
                    threading.Thread(
                        target=self._fetch_slice, args=(key,), daemon=True
                    ).start()

        self._prefetch_adjacent(ue)

        return 1

    def _put_cache(self, key, data):
        with self._lock:
            self._cache[key] = data
            if len(self._cache) > self._cache_max:
                self._cache.popitem(last=False)

    def _prefetch_adjacent(self, current_extent):
        """Prefetch ±N slices around the current position."""
        x0, x1, y0, y1, z0, z1 = current_extent

        # Determine which axis is the slice axis (extent size = 1)
        if z0 == z1:
            axis, idx, lo, hi = "z", z0, 0, self._shape[0] - 1
        elif y0 == y1:
            axis, idx, lo, hi = "y", y0, 0, self._shape[1] - 1
        elif x0 == x1:
            axis, idx, lo, hi = "x", x0, 0, self._shape[2] - 1
        else:
            return

        for offset in (1, -1, 2, -2):
            nidx = idx + offset
            if nidx < lo or nidx > hi:
                continue

            if axis == "z":
                key = (x0, x1, y0, y1, nidx, nidx)
            elif axis == "y":
                key = (x0, x1, nidx, nidx, z0, z1)
            else:
                key = (nidx, nidx, y0, y1, z0, z1)

            with self._lock:
                if key in self._cache or key in self._pending:
                    continue
                self._pending.add(key)

            thread = threading.Thread(
                target=self._fetch_slice, args=(key,), daemon=True
            )
            thread.start()

    def _fetch_slice(self, key):
        """Background fetch of a single slice."""
        x0, x1, y0, y1, z0, z1 = key
        try:
            slab = self._arr[z0 : z1 + 1, y0 : y1 + 1, x0 : x1 + 1]
            flat = np.ascontiguousarray(slab, dtype=np.float32).ravel(order="F")
            self._put_cache(key, flat)
        except Exception:
            pass
        finally:
            with self._lock:
                self._pending.discard(key)

        if self._on_slice_ready is not None:
            self._on_slice_ready()


def open_omezarr(url, level=-1, on_slice_ready=None):
    """
    Open a remote OME-Zarr store and return a VTK streaming source.

    Parameters
    ----------
    url : str
        S3 (``s3://...``) or HTTPS URL to an OME-Zarr directory.
    level : int
        Resolution level. ``0`` = full, ``-1`` = lowest (fastest).
    on_slice_ready : callable, optional
        Called when a prefetched slice becomes available.

    Returns
    -------
    source : ZarrImageSource
    info : dict
        Metadata: ``shape``, ``spacing``, ``levels``, ``current_level``.
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

    if level == -1:
        level = len(levels) - 1
    level = max(0, min(level, len(levels) - 1))

    chosen = levels[level]
    source = ZarrImageSource(
        chosen["array"],
        chosen["spacing"],
        on_slice_ready=on_slice_ready,
    )

    info = {
        "shape": chosen["shape"],
        "spacing": chosen["spacing"],
        "levels": [
            {"path": level["path"], "shape": level["shape"], "spacing": level["spacing"]}
            for level in levels
        ],
        "current_level": level,
    }

    return source, info
