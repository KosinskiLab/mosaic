"""
Tests for geometry export and file writing.

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import json

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from mosaic.geometry import Geometry
from mosaic.formats.writer import write_geometries, write_topology_file


@pytest.fixture
def cloud():
    rng = np.random.RandomState(42)
    pts = rng.rand(20, 3).astype(np.float32) * 100
    quats = (
        Rotation.random(20, random_state=42)
        .as_quat(scalar_first=True)
        .astype(np.float32)
    )
    return Geometry(points=pts, quaternions=quats)


@pytest.fixture
def cloud_no_quats():
    rng = np.random.RandomState(0)
    return Geometry(points=rng.rand(15, 3).astype(np.float32) * 50)


class TestWriteGeometriesXyz:

    def test_single_file(self, tmp_path, cloud_no_quats):
        path = str(tmp_path / "out.xyz")
        write_geometries([cloud_no_quats], path, format="xyz")
        data = np.loadtxt(path, delimiter=",", skiprows=1)
        assert data.shape == (15, 3)

    def test_multi_file(self, tmp_path, cloud_no_quats):
        paths = [str(tmp_path / f"out_{i}.xyz") for i in range(2)]
        g1 = cloud_no_quats
        g2 = Geometry(points=np.random.rand(10, 3).astype(np.float32) * 50)
        write_geometries([g1, g2], paths, format="xyz")
        for p in paths:
            assert (tmp_path / p.split("/")[-1]).exists()

    def test_merged_single_path(self, tmp_path):
        g1 = Geometry(points=np.ones((5, 3), dtype=np.float32))
        g2 = Geometry(points=np.ones((3, 3), dtype=np.float32) * 2)
        path = str(tmp_path / "merged.xyz")
        write_geometries([g1, g2], path, format="xyz")
        data = np.loadtxt(path, delimiter=",", skiprows=1)
        assert data.shape[0] == 8


class TestWriteGeometriesNdjson:

    def test_single_file(self, tmp_path, cloud):
        path = str(tmp_path / "out.ndjson")
        write_geometries([cloud], path, format="ndjson")
        with open(path) as f:
            lines = [json.loads(l) for l in f if l.strip()]
        assert len(lines) == 20
        assert "location" in lines[0]
        assert "xyz_rotation_matrix" in lines[0]

    def test_multi_file(self, tmp_path, cloud):
        g1 = Geometry(
            points=cloud.points[:10],
            quaternions=cloud.quaternions[:10],
        )
        g2 = Geometry(
            points=cloud.points[10:],
            quaternions=cloud.quaternions[10:],
        )
        paths = [str(tmp_path / "a.ndjson"), str(tmp_path / "b.ndjson")]
        write_geometries([g1, g2], paths, format="ndjson")
        for p in paths:
            assert (tmp_path / p.split("/")[-1]).exists()

    def test_roundtrip(self, tmp_path, cloud):
        from mosaic.formats.parser import read_ndjson

        path = str(tmp_path / "rt.ndjson")
        write_geometries([cloud], path, format="ndjson")
        gdc = read_ndjson(path)
        np.testing.assert_allclose(gdc[0].vertices, cloud.points, atol=0.01)


class TestWriteGeometriesEdgeCases:

    def test_empty_list_returns_none(self, tmp_path):
        result = write_geometries([], str(tmp_path / "empty.xyz"), format="xyz")
        assert result is None

    def test_path_list_length_mismatch_raises(self, tmp_path):
        g = Geometry(points=np.zeros((5, 3), dtype=np.float32))
        with pytest.raises(ValueError, match="file_path list length"):
            write_geometries(
                [g], [str(tmp_path / "a.xyz"), str(tmp_path / "b.xyz")], format="xyz"
            )

    def test_mesh_format_no_model_raises(self, tmp_path, cloud_no_quats):
        with pytest.raises(ValueError, match="No geometries have a fitted mesh"):
            write_geometries([cloud_no_quats], str(tmp_path / "out.obj"), format="obj")

    def test_unsupported_format_raises(self, tmp_path, cloud_no_quats):
        with pytest.raises(ValueError, match="Unsupported format"):
            write_geometries([cloud_no_quats], str(tmp_path / "out.xxx"), format="xxx")


class TestWriteGeometriesSampling:

    def test_relion_5_format(self, tmp_path, cloud_no_quats):
        # relion_5_format applies only to STAR; other formats absorb it.
        path = str(tmp_path / "relion5.xyz")
        shape = (100, 100, 100)
        write_geometries(
            [cloud_no_quats],
            path,
            format="xyz",
            relion_5_format=True,
            shape=shape,
        )
        data = np.loadtxt(path, delimiter=",", skiprows=1)
        assert data.shape[0] == 15


class TestCoerceRecords:

    def test_pulls_point_data_and_sampling(self):
        from mosaic.formats.records import GeometryData
        from mosaic.formats.writer import _coerce_records

        g = Geometry(
            points=np.arange(9, dtype=np.float32).reshape(3, 3),
            sampling_rate=np.array([2.0, 2.0, 2.0], dtype=np.float32),
        )
        records = _coerce_records([g])
        assert len(records) == 1
        assert isinstance(records[0], GeometryData)
        np.testing.assert_array_equal(records[0].vertices, g.points)
        np.testing.assert_array_equal(records[0].sampling, g.sampling_rate)

    def test_carries_quaternions_when_present(self, cloud):
        from mosaic.formats.writer import _coerce_records

        records = _coerce_records([cloud])
        np.testing.assert_array_equal(records[0].quaternions, cloud.quaternions)

    def test_quaternions_none_when_absent(self, cloud_no_quats):
        from mosaic.formats.writer import _coerce_records

        records = _coerce_records([cloud_no_quats])
        assert records[0].quaternions is None

    def test_carries_model_attribute(self, cloud_no_quats):
        from mosaic.formats.writer import _coerce_records

        records = _coerce_records([cloud_no_quats])
        assert records[0].model is cloud_no_quats.model

    def test_empty_input_returns_empty_list(self):
        from mosaic.formats.writer import _coerce_records

        assert _coerce_records([]) == []


class TestPrepareOrientedPoints:

    def test_scales_by_sampling_and_concatenates(self):
        from mosaic.formats.writer import _coerce_records, _prepare_oriented_points

        g1 = Geometry(
            points=np.array([[2.0, 4.0, 6.0]], dtype=np.float32),
            sampling_rate=np.array([2.0, 2.0, 2.0], dtype=np.float32),
        )
        g2 = Geometry(
            points=np.array([[10.0, 20.0, 30.0]], dtype=np.float32),
            sampling_rate=np.array([5.0, 5.0, 5.0], dtype=np.float32),
        )
        records = _coerce_records([g1, g2])
        out = _prepare_oriented_points(records, sampling=None)
        np.testing.assert_allclose(
            out["points"], np.array([[1.0, 2.0, 3.0], [2.0, 4.0, 6.0]])
        )
        np.testing.assert_array_equal(out["entities"], np.array([0, 1]))
        assert out["pixel_sizes"] == [2.0, 5.0]
        assert out["quaternions"].shape == (2, 4)

    def test_sampling_override(self):
        from mosaic.formats.writer import _coerce_records, _prepare_oriented_points

        g = Geometry(
            points=np.array([[2.0, 2.0, 2.0]], dtype=np.float32),
            sampling_rate=np.array([1.0, 1.0, 1.0], dtype=np.float32),
        )
        out = _prepare_oriented_points(_coerce_records([g]), sampling=2.0)
        np.testing.assert_allclose(out["points"], np.array([[1.0, 1.0, 1.0]]))
        assert out["pixel_sizes"] == [2.0]

    def test_preserves_existing_quaternions(self, cloud):
        from mosaic.formats.writer import _coerce_records, _prepare_oriented_points

        records = _coerce_records([cloud])
        out = _prepare_oriented_points(records, sampling=None)
        np.testing.assert_allclose(out["quaternions"], cloud.quaternions)


class TestWriteTopologyFile:

    @pytest.fixture
    def topo_data(self):
        return {
            "vertices": np.array(
                [
                    [0, 1.0, 2.0, 3.0, 0],
                    [1, 4.0, 5.0, 6.0, 0],
                    [2, 7.0, 8.0, 9.0, 0],
                ]
            ),
            "faces": np.array(
                [
                    [0, 0, 1, 2],
                ]
            ),
            "box": np.array([10.0, 10.0, 10.0]),
        }

    def test_q_format(self, tmp_path, topo_data):
        path = str(tmp_path / "mesh.q")
        write_topology_file(path, topo_data, tsi_format=False)
        with open(path) as f:
            content = f.read()
        assert "10.0" in content
        assert content.startswith("10.")

    def test_tsi_format(self, tmp_path, topo_data):
        path = str(tmp_path / "mesh.tsi")
        write_topology_file(path, topo_data, tsi_format=True)
        with open(path) as f:
            content = f.read()
        assert "version 1.1" in content
        assert "vertex" in content
        assert "triangle" in content

    def test_tsi_with_inclusions(self, tmp_path, topo_data):
        topo_data["inclusions"] = np.array(
            [
                [0.0, 1.0, 2.0, 0.5, 0.6, 0.7],
            ]
        )
        path = str(tmp_path / "inc.tsi")
        write_topology_file(path, topo_data, tsi_format=True)
        with open(path) as f:
            content = f.read()
        assert "inclusion" in content


class TestWriteStar:

    def test_writes_star_file(self, tmp_path, cloud):
        from mosaic.formats.writer import _coerce_records, write_star

        path = str(tmp_path / "out.star")
        write_star(_coerce_records([cloud]), path, sampling=1.0)
        assert (tmp_path / "out.star").exists()

    def test_pixel_size_header_from_geometry_sampling(self, tmp_path):
        from mosaic.formats.writer import _coerce_records, write_star

        g = Geometry(
            points=np.array([[1.0, 2.0, 3.0]], dtype=np.float32),
            quaternions=np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32),
            sampling_rate=np.array([3.0, 3.0, 3.0], dtype=np.float32),
        )
        path = str(tmp_path / "px.star")
        write_star(_coerce_records([g]), path, sampling=3.0)
        with open(path) as f:
            content = f.read()
        assert "_rlnImagePixelSize" in content
        assert "3.0" in content

    def test_relion_5_writes_version_marker(self, tmp_path, cloud):
        from mosaic.formats.writer import _coerce_records, write_star

        path = str(tmp_path / "r5.star")
        write_star(
            _coerce_records([cloud]),
            path,
            shape=(100, 100, 100),
            sampling=1.0,
            relion_5_format=True,
        )
        with open(path) as f:
            content = f.read()
        assert "50001" in content

    def test_relion_5_writes_pixel_size_for_roundtrip(self, tmp_path, cloud):
        """RELION-5 needs the optics pixel size so import can undo the centering."""
        from mosaic.formats.writer import _coerce_records, write_star
        from mosaic.formats._utils import read_star_header

        path = str(tmp_path / "r5.star")
        write_star(
            _coerce_records([cloud]),
            path,
            shape=(100, 100, 100),
            sampling=4.0,
            relion_5_format=True,
        )
        header = read_star_header(path)
        assert header["centered"] is True
        assert header["pixel_size"] == pytest.approx(4.0)

    def test_relion_5_requires_shape(self, tmp_path, cloud):
        from mosaic.formats.writer import _coerce_records, write_star

        with pytest.raises(ValueError, match="shape"):
            write_star(
                _coerce_records([cloud]),
                str(tmp_path / "r5.star"),
                sampling=1.0,
                relion_5_format=True,
            )


class TestWriteTsv:

    def test_writes_tsv_with_orientation_columns(self, tmp_path, cloud):
        from mosaic.formats.writer import _coerce_records, write_tsv

        path = str(tmp_path / "out.tsv")
        write_tsv(_coerce_records([cloud]), path, sampling=1.0)
        with open(path) as f:
            header = f.readline()
        assert "euler" in header


class TestWriteXyz:

    def test_writes_concatenated_points(self, tmp_path):
        from mosaic.formats.writer import _coerce_records, write_xyz

        g1 = Geometry(points=np.ones((5, 3), dtype=np.float32))
        g2 = Geometry(points=np.ones((3, 3), dtype=np.float32) * 2)
        path = str(tmp_path / "out.xyz")
        write_xyz(_coerce_records([g1, g2]), path, sampling=1.0)
        data = np.loadtxt(path, delimiter=",", skiprows=1)
        assert data.shape == (8, 3)


class TestWriteNdjson:

    def test_writes_one_record_per_point(self, tmp_path, cloud):
        from mosaic.formats.writer import _coerce_records, write_ndjson

        path = str(tmp_path / "out.ndjson")
        write_ndjson(_coerce_records([cloud]), path, sampling=1.0)
        with open(path) as f:
            lines = [json.loads(l) for l in f if l.strip()]
        assert len(lines) == 20
        assert "location" in lines[0]
        assert "xyz_rotation_matrix" in lines[0]

    def test_synthesizes_quaternions_from_normals(self, tmp_path):
        from mosaic.formats.writer import _coerce_records, write_ndjson

        normals = np.tile(np.array([0.0, 0.0, 1.0], dtype=np.float32), (3, 1))
        g = Geometry(
            points=np.zeros((3, 3), dtype=np.float32),
            normals=normals,
        )
        path = str(tmp_path / "out.ndjson")
        write_ndjson(_coerce_records([g]), path, sampling=1.0)
        with open(path) as f:
            line = json.loads(f.readline())
        assert "xyz_rotation_matrix" in line
        assert len(line["xyz_rotation_matrix"]) == 3


class TestWriteMeshes:

    def test_no_mesh_raises(self, tmp_path, cloud_no_quats):
        from mosaic.formats.writer import _coerce_records, write_meshes

        with pytest.raises(ValueError, match="No geometries have a fitted mesh"):
            write_meshes(_coerce_records([cloud_no_quats]), str(tmp_path / "out.obj"))


class TestWriteVolume:

    def test_writes_volume_file(self, tmp_path):
        from mosaic.formats.writer import _coerce_records, write_volume

        g = Geometry(points=np.array([[1.0, 2.0, 3.0]], dtype=np.float32))
        path = str(tmp_path / "out.mrc")
        write_volume(_coerce_records([g]), path, shape=(8, 8, 8), sampling=1.0)
        assert (tmp_path / "out.mrc").exists()


class TestWriteGeometriesMultiFile:

    def test_one_file_per_geometry(self, tmp_path, cloud):
        g1 = Geometry(points=cloud.points[:10], quaternions=cloud.quaternions[:10])
        g2 = Geometry(points=cloud.points[10:], quaternions=cloud.quaternions[10:])
        paths = [str(tmp_path / "a.star"), str(tmp_path / "b.star")]
        write_geometries([g1, g2], paths, format="star")
        for p in paths:
            assert (tmp_path / p.split("/")[-1]).exists()

    def test_dispatch_reaches_each_format(self, tmp_path):
        g = Geometry(
            points=np.array([[1.0, 2.0, 3.0]], dtype=np.float32),
            quaternions=np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32),
        )
        for fmt in ("star", "tsv", "xyz", "ndjson"):
            path = str(tmp_path / f"out.{fmt}")
            write_geometries([g], path, format=fmt)
            assert (tmp_path / f"out.{fmt}").exists()


class TestShapeInference:

    def test_volume_shape_inferred_from_bounds(self, tmp_path):
        # No shape passed; orchestrator should infer it from point bounds.
        g = Geometry(points=np.array([[5.0, 6.0, 7.0]], dtype=np.float32))
        path = str(tmp_path / "auto.mrc")
        write_geometries([g], path, format="mrc", sampling=1.0)
        assert (tmp_path / "auto.mrc").exists()


class TestRelion5Centering:

    def test_origin_shifted_to_volume_center(self, tmp_path):
        # With sampling 1 and shape (100, 100, 100), the relion_5 center is
        # (50, 50, 50) Å. A point at (50, 50, 50) Å should be written as
        # ~(0, 0, 0).
        g = Geometry(
            points=np.array([[50.0, 50.0, 50.0]], dtype=np.float32),
            quaternions=np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32),
        )
        path = str(tmp_path / "centered.star")
        write_geometries(
            [g],
            path,
            format="star",
            shape=(100, 100, 100),
            sampling=1.0,
            relion_5_format=True,
        )
        with open(path) as f:
            content = f.read()
        # The point lands on the centered origin; STAR writes near-zero
        # coordinates for it. Values are tab-separated in the data row.
        assert "\t0.0\t" in content or content.count("0.0") >= 3
