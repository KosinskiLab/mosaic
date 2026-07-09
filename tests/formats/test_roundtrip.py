"""
Tests for file format read/write roundtrips and format detection.

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import json
import struct

import numpy as np
import pytest

from mosaic.geometry import Geometry, GeometryData
from mosaic.formats.parser import (
    NotASegmentationError,
    points_from_flat_array,
    read_mrc_dtype,
    read_ndjson,
    read_star,
    read_txt,
)
from mosaic.formats.parser import resolve_parser
from mosaic.formats.reader import open_file, is_volume_file, is_likely_density_map
from mosaic.formats.writer import write_geometries


class TestNdjsonRoundTrip:
    def test_oriented_points(self, tmp, points, quaternions):
        g = Geometry(points=points, quaternions=quaternions)
        path = f"{tmp}.ndjson"
        write_geometries([g], path, format="ndjson")

        gdc = read_ndjson(path)
        np.testing.assert_allclose(gdc[0].vertices, points, atol=0.01)
        assert gdc[0].quaternions is not None

    def test_point_records(self, tmp):
        path = f"{tmp}.ndjson"
        records = [
            {"type": "point", "location": {"x": 1.0, "y": 2.0, "z": 3.0}},
            {"type": "point", "location": {"x": 4.0, "y": 5.0, "z": 6.0}},
        ]
        with open(path, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        gdc = read_ndjson(path)
        assert gdc[0].vertices.shape == (2, 3)
        np.testing.assert_allclose(gdc[0].vertices[0], [1, 2, 3])

    def test_instance_segmentation(self, tmp):
        path = f"{tmp}.ndjson"
        records = [
            {"location": {"x": 0, "y": 0, "z": 0}, "instance_id": 1},
            {"location": {"x": 1, "y": 1, "z": 1}, "instance_id": 1},
            {"location": {"x": 5, "y": 5, "z": 5}, "instance_id": 2},
        ]
        with open(path, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        gdc = read_ndjson(path)
        assert len(gdc) == 2
        assert gdc[0].vertex_properties is not None

    def test_empty_file(self, tmp):
        path = f"{tmp}.ndjson"
        with open(path, "w") as f:
            f.write("")
        gdc = read_ndjson(path)
        assert len(gdc) == 1
        assert gdc[0].vertices.shape[0] == 0

    def test_open_file_dispatch(self, tmp, points, quaternions):
        g = Geometry(points=points, quaternions=quaternions)
        path = f"{tmp}.ndjson"
        write_geometries([g], path, format="ndjson")
        gdc = open_file(path)
        assert gdc[0].vertices.shape == (20, 3)


class TestXyzRoundTrip:
    def test_write_read(self, tmp, points):
        g = Geometry(points=points)
        path = f"{tmp}.xyz"
        write_geometries([g], path, format="xyz")

        gdc = read_txt(path)
        np.testing.assert_allclose(gdc[0].vertices, points, atol=0.01)


class TestStarRoundTrip:
    def test_write_read(self, tmp, geom):
        path = f"{tmp}.star"
        write_geometries([geom], path, format="star")
        gdc = open_file(path)
        assert gdc[0].vertices.shape[0] == 20


class TestMeshRoundTrip:
    @pytest.mark.parametrize("fmt", ["obj", "ply"])
    def test_write_read(self, tmp, fmt):
        from mosaic.operations import fit

        pts = (
            np.array(
                [
                    [np.sin(t) * np.cos(p), np.sin(t) * np.sin(p), np.cos(t)]
                    for t in np.linspace(0.1, np.pi - 0.1, 15)
                    for p in np.linspace(0, 2 * np.pi, 15, endpoint=False)
                ],
                dtype=np.float32,
            )
            * 50
        )
        gd = fit(GeometryData(points=pts), method="alpha_shape", alpha=1.0)
        g = Geometry(points=gd.points, model=gd.model)

        path = f"{tmp}.{fmt}"
        write_geometries([g], path, format=fmt)
        gdc = open_file(path)
        assert gdc[0].vertices.shape[0] > 0
        assert gdc[0].faces is not None

    def test_no_mesh_raises(self, tmp):
        g = Geometry(points=np.zeros((10, 3), dtype=np.float32))
        with pytest.raises(ValueError, match="No geometries have a fitted mesh"):
            write_geometries([g], f"{tmp}.obj", format="obj")


class TestMultiFileExport:
    def test_separate_files(self, tmp, points, quaternions):
        g1 = Geometry(points=points[:10], quaternions=quaternions[:10])
        g2 = Geometry(points=points[10:], quaternions=quaternions[10:])
        paths = [f"{tmp}_0.ndjson", f"{tmp}_1.ndjson"]
        write_geometries([g1, g2], paths, format="ndjson")

        import os

        for p in paths:
            assert os.path.exists(p)
        gdc0 = read_ndjson(paths[0])
        gdc1 = read_ndjson(paths[1])
        assert gdc0[0].vertices.shape[0] == 10
        assert gdc1[0].vertices.shape[0] == 10


class TestOpenFileDispatch:
    def test_unknown_extension(self):
        with pytest.raises(ValueError, match="Unknown extension"):
            open_file("file.banana")

    def test_is_volume_file(self):
        assert is_volume_file("scan.mrc")
        assert is_volume_file("scan.mrc.gz")
        assert not is_volume_file("data.star")

    def test_all_formats_registered(self):
        for ext in ("star", "tsv", "xyz", "obj", "ply", "ndjson", "mrc", "vtu"):
            assert resolve_parser(ext) is not None, f"{ext} has no registered parser"


class TestPointsFromFlatArray:
    def test_raises_when_too_many_unique_values(self):
        arr = np.arange(20_000, dtype=np.int32)
        dims = (20, 20, 50)
        with pytest.raises(NotASegmentationError) as excinfo:
            points_from_flat_array(arr, dims, max_cluster=100)
        msg = str(excinfo.value)
        assert "max_cluster" in msg or "100" in msg

    def test_returns_empty_for_all_zero_array(self):
        arr = np.zeros(1000, dtype=np.int32)
        dims = (10, 10, 10)
        result = points_from_flat_array(arr, dims)
        assert result == []

    def test_returns_per_label_arrays_for_small_segmentation(self):
        arr = np.zeros(64, dtype=np.int32)
        arr[0:10] = 1
        arr[10:20] = 2
        dims = (4, 4, 4)
        result = points_from_flat_array(arr, dims)
        assert len(result) == 2
        assert all(pts.shape[1] == 3 for pts in result)


def test_not_a_segmentation_error_reexport():
    from mosaic.formats import NotASegmentationError as Reexported
    from mosaic.formats.parser import NotASegmentationError as Direct

    assert Reexported is Direct


def _write_mrc(path, nx, ny, nz, mode, data):
    """Write a minimal valid MRC file."""
    header = bytearray(1024)
    struct.pack_into("<3i", header, 0, nx, ny, nz)
    struct.pack_into("<i", header, 12, mode)
    struct.pack_into("<3f", header, 40, float(nx), float(ny), float(nz))
    struct.pack_into("<3i", header, 64, 1, 2, 3)
    struct.pack_into("<i", header, 92, 0)
    header[208:212] = b"MAP "
    path.write_bytes(bytes(header) + data.tobytes())


class TestReadMrcDtype:
    def test_float32_mrc(self, tmp_path):
        path = tmp_path / "float.mrc"
        _write_mrc(path, 4, 4, 4, 2, np.zeros(64, dtype=np.float32))
        assert read_mrc_dtype(str(path)) is np.float32

    def test_int16_mrc(self, tmp_path):
        path = tmp_path / "int.mrc"
        _write_mrc(path, 4, 4, 4, 1, np.zeros(64, dtype=np.int16))
        assert read_mrc_dtype(str(path)) is np.int16

    def test_non_mrc_returns_none(self, tmp_path):
        path = tmp_path / "fake.mrc"
        path.write_bytes(b"\x00" * 512)
        assert read_mrc_dtype(str(path)) is None


class TestIsLikelyDensityMap:
    def test_float_mrc_is_density(self, tmp_path):
        path = tmp_path / "density.mrc"
        _write_mrc(path, 4, 4, 4, 2, np.zeros(64, dtype=np.float32))
        assert is_likely_density_map(str(path)) is True

    def test_int16_segmentation_is_not_density(self, tmp_path):
        path = tmp_path / "seg.mrc"
        arr = np.array([0, 1, 2] * 333 + [0], dtype=np.int16)
        _write_mrc(path, 10, 10, 10, 1, arr)
        assert is_likely_density_map(str(path)) is False

    def test_int16_many_unique_is_density(self, tmp_path):
        path = tmp_path / "quant.mrc"
        arr = np.arange(200_000, dtype=np.int16)
        _write_mrc(path, 100, 100, 20, 1, arr)
        assert is_likely_density_map(str(path)) is True

    def test_non_volume_returns_false(self, tmp_path):
        path = tmp_path / "data.star"
        path.write_text("data_\nloop_\n_rlnX\n1.0\n")
        assert is_likely_density_map(str(path)) is False


class TestReadStarSampling:
    """``read_star`` populates ``GeometryDataContainer.sampling`` from the optics block."""

    OPTICS_STAR = (
        "data_optics\n"
        "loop_\n"
        "_rlnOpticsGroup #1\n"
        "_rlnImagePixelSize #2\n"
        "1 6.43832\n"
        "\n"
        "data_particles\n"
        "loop_\n"
        "_rlnCoordinateX #1\n"
        "_rlnCoordinateY #2\n"
        "_rlnCoordinateZ #3\n"
        "_rlnAngleRot #4\n"
        "_rlnAngleTilt #5\n"
        "_rlnAnglePsi #6\n"
        "100.0 200.0 300.0 0.0 0.0 0.0\n"
    )

    LEGACY_STAR = (
        "data_\n"
        "loop_\n"
        "_rlnCoordinateX #1\n"
        "_rlnCoordinateY #2\n"
        "_rlnCoordinateZ #3\n"
        "_rlnAngleRot #4\n"
        "_rlnAngleTilt #5\n"
        "_rlnAnglePsi #6\n"
        "100.0 200.0 300.0 0.0 0.0 0.0\n"
    )

    def test_optics_pixel_size_drives_container_sampling(self, tmp_path):
        path = tmp_path / "particles.star"
        path.write_text(self.OPTICS_STAR)

        container = read_star(str(path))

        np.testing.assert_array_equal(container.sampling, (6.43832, 6.43832, 6.43832))

    def test_no_optics_block_keeps_default_sampling(self, tmp_path):
        path = tmp_path / "legacy.star"
        path.write_text(self.LEGACY_STAR)

        container = read_star(str(path))

        np.testing.assert_array_equal(container.sampling, (1, 1, 1))
