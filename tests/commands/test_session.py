"""
Tests for the headless Session state manager.

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import numpy as np
import pytest

from mosaic.commands.session import Session
from mosaic.geometry import Geometry


def _geom(n_points=50, seed=None):
    rng = np.random.RandomState(seed)
    return Geometry(points=rng.rand(n_points, 3).astype(np.float32) * 100)


class TestResolve:

    @pytest.mark.parametrize(
        "spec, expected_len",
        [
            ("*", 3),
            ("#0", 1),
            ("#1-2", 2),
        ],
    )
    def test_valid_specs(self, make_session, spec, expected_len):
        session = make_session(n=3)
        assert len(session.resolve(spec)) == expected_len

    def test_at_last(self, make_session):
        session = make_session(n=1)
        geom = _geom()
        session._last_results = [geom]
        assert session.resolve("@last") == [geom]

    def test_out_of_range(self, make_session):
        session = make_session(n=1)
        with pytest.raises(IndexError):
            session.resolve("#99")

    def test_invalid_spec(self):
        with pytest.raises(ValueError, match="Invalid target"):
            Session().resolve("bad")

    def test_resolve_many_deduplicates(self, make_session):
        session = make_session(n=3)
        assert len(session.resolve_many(["#0", "#0", "#1"])) == 2


class TestApply:

    def test_downsample_creates_geometry(self, make_session):
        session = make_session(n=1, n_points=200)
        geoms = session.resolve("*")
        created = session.apply(
            "downsample", geoms, method="number", size=50, workers=1
        )
        assert len(created) == 1
        assert created[0].get_number_of_points() == 50
        assert created[0] in session._all_geometries()

    def test_persist_false(self, make_session):
        session = make_session(n=1, n_points=200)
        geoms = session.resolve("*")
        initial_count = len(session._all_geometries())
        created = session.apply(
            "downsample", geoms, method="number", size=50, persist=False, workers=1
        )
        assert len(created) == 1
        assert len(session._all_geometries()) == initial_count
        assert session.resolve("@last") == created

    def test_duplicate(self, make_session):
        session = make_session(n=1, n_points=30)
        geoms = session.resolve("*")
        created = session.apply("duplicate", geoms, workers=1)
        assert len(created) == 1
        assert created[0].get_number_of_points() == 30
        assert len(session._all_geometries()) == 2

    def test_unknown_operation(self, make_session):
        session = make_session(n=1)
        with pytest.raises(ValueError, match="Unknown operation"):
            session.apply("nonexistent", session.resolve("*"))


class TestMeasure:

    def test_scalar_property(self, make_session):
        session = make_session(n=1, n_points=77)
        results = session.measure("n_points", session._all_geometries())
        assert results == [77]

    def test_per_vertex_property(self, make_session):
        session = make_session(n=1, n_points=50)
        geoms = session._all_geometries()
        results = session.measure("height", geoms)
        assert isinstance(results[0], np.ndarray)
        assert len(results[0]) == 50

    def test_store_per_vertex(self, make_session):
        session = make_session(n=1, n_points=50)
        geoms = session._all_geometries()
        session.measure("height", geoms, store=True)
        stored = geoms[0].vertex_properties.get_property("height")
        assert stored is not None and len(stored) == 50

    def test_store_scalar_skips(self, make_session):
        session = make_session(n=1, n_points=50)
        geoms = session._all_geometries()
        session.measure("n_points", geoms, store=True)
        assert geoms[0].vertex_properties.get_property("n_points") is None


class TestFilter:

    def test_population_level(self):
        session = Session(quiet=True)
        for size in [50, 200, 300]:
            g = _geom(size, seed=size)
            session._data.add(g)
            session._order.append(g)
        geoms = session._all_geometries()
        kept, removed, level = session.filter(geoms, "n_points", lower=100)
        assert (kept, removed, level) == (2, 1, "population")
        assert len(session._all_geometries()) == 2

    def test_point_level(self, make_session):
        session = make_session(n=1, n_points=100)
        geoms = session._all_geometries()
        session.measure("height", geoms, store=True)
        heights = geoms[0].vertex_properties.get_property("height")
        median = float(np.median(heights))
        kept, removed, level = session.filter(geoms, "height", lower=median)
        assert level == "point"
        assert kept > 0 and removed > 0

    def test_updates_last_results(self):
        session = Session(quiet=True)
        for size in [50, 200]:
            g = _geom(size, seed=size)
            session._data.add(g)
            session._order.append(g)
        geoms = session._all_geometries()
        session.filter(geoms, "n_points", lower=100)
        assert len(session._last_results) == 1
        assert session._last_results[0].get_number_of_points() == 200


class TestMerge:

    def test_merge_preserves_total_points(self, make_session):
        session = make_session(n=2, n_points=50)
        geoms = session._all_geometries()
        merged = session.merge(geoms, name="merged")
        assert merged.get_number_of_points() == 100
        assert merged._meta["name"] == "merged"
        assert len(session._all_geometries()) == 1

    def test_merge_updates_last(self, make_session):
        session = make_session(n=2, n_points=10)
        merged = session.merge(session._all_geometries())
        assert session._last_results == [merged]


class TestGrouping:

    def test_create_group(self, make_session):
        session = make_session(n=3)
        geoms = session._all_geometries()
        gid = session.group(geoms[:2], "Alpha")
        assert len(session._data_tree.groups[gid]) == 2
        assert session._data_tree.group_names[gid] == "Alpha"

    def test_move_cleans_empty_group(self, make_session):
        session = make_session(n=3)
        geoms = session._all_geometries()
        session.group(geoms[:2], "Alpha")
        session.group(geoms[2:], "Beta")
        session.group(geoms[:2], "Beta")
        names = set(session._data_tree.group_names.values())
        assert "Alpha" not in names
        assert "Beta" in names

    def test_ungroup_all(self, make_session):
        session = make_session(n=3)
        geoms = session._all_geometries()
        session.group(geoms, "All")
        count = session.ungroup(geoms)
        assert count == 3
        assert len(session._data_tree.groups) == 0

    def test_group_empty_raises(self):
        with pytest.raises(ValueError, match="No geometries"):
            Session().group([], "Empty")


class TestRemove:

    def test_remove_clears_order_and_last(self, make_session):
        session = make_session(n=2)
        geoms = session._all_geometries()
        session._last_results = list(geoms)
        session.remove([geoms[0]])
        assert len(session._all_geometries()) == 1
        assert len(session._last_results) == 1

    def test_remove_cleans_tree(self, make_session):
        session = make_session(n=2)
        geoms = session._all_geometries()
        session.group(geoms, "G")
        session.remove([geoms[0]])
        for members in session._data_tree.groups.values():
            assert geoms[0].uuid not in members


class TestListFiltered:

    def test_visibility_filter(self, make_session):
        session = make_session(n=3)
        session._all_geometries()[0].set_visibility(False)
        assert len(session.list_filtered(visible=True)) == 2
        assert len(session.list_filtered(visible=None)) == 3

    def test_name_filter(self, make_session):
        session = make_session(n=3)
        assert len(session.list_filtered(name="cloud_1")) == 1
        assert len(session.list_filtered(name="cloud_*")) == 3

    def test_re_show(self, make_session):
        session = make_session(n=2)
        g = session._all_geometries()[0]
        g.set_visibility(False)
        assert len(session.list_filtered(visible=True)) == 1
        g.set_visibility(True)
        assert len(session.list_filtered(visible=True)) == 2


class TestLog:

    def test_log_appends(self):
        s = Session()
        s.log_command("list")
        s.log_command("info #0")
        assert s._log == ["list", "info #0"]


class TestHelpers:

    def test_flatten_nested(self):
        assert Session._flatten([[1, 2], 3, [4]]) == [1, 2, 3, 4]

    def test_flatten_already_flat(self):
        assert Session._flatten([1, 2, 3]) == [1, 2, 3]

    def test_flatten_empty(self):
        assert Session._flatten([]) == []

    def test_owner_data(self, make_session):
        session = make_session(n=1)
        g = session._all_geometries()[0]
        assert session._owner(g) is session._data

    def test_owner_not_found(self, make_session):
        session = make_session(n=1)
        orphan = _geom(10)
        assert session._owner(orphan) is None

    def test_tree_for_data(self, make_session):
        session = make_session(n=1)
        assert session._tree_for(session._data) is session._data_tree

    def test_tree_for_models(self, make_session):
        session = make_session(n=1)
        assert session._tree_for(session._models) is session._models_tree

    def test_geometry_name_default_cluster(self, make_session):
        session = make_session(n=1)
        g = session._all_geometries()[0]
        g._meta.pop("name", None)
        assert "Cluster" in session._geometry_name(g, 0)

    def test_geometry_name_explicit(self, make_session):
        session = make_session(n=1)
        g = session._all_geometries()[0]
        assert session._geometry_name(g, 0) == "cloud_0"

    def test_geometry_group_empty(self, make_session):
        session = make_session(n=1)
        g = session._all_geometries()[0]
        assert session._geometry_group(g) == ""

    def test_geometry_group_assigned(self, make_session):
        session = make_session(n=1)
        g = session._all_geometries()[0]
        session.group([g], "MyGroup")
        assert session._geometry_group(g) == "MyGroup"


class TestMatchFilter:

    def test_substring_match(self):
        assert Session._match_filter("cloud_data_123", "data") is True

    def test_substring_case_insensitive(self):
        assert Session._match_filter("Cloud_Data", "cloud") is True

    def test_glob_match(self):
        assert Session._match_filter("cloud_0", "cloud_*") is True

    def test_glob_question_mark(self):
        assert Session._match_filter("cloud_0", "cloud_?") is True

    def test_no_match(self):
        assert Session._match_filter("alpha", "beta") is False


class TestListFilteredExtended:

    def test_group_filter(self, make_session):
        session = make_session(n=3)
        geoms = session._all_geometries()
        session.group(geoms[:2], "Alpha")
        assert len(session.list_filtered(group="Alpha")) == 2
        assert len(session.list_filtered(group="Beta")) == 0

    def test_hidden_filter(self, make_session):
        session = make_session(n=3)
        session._all_geometries()[0].set_visibility(False)
        assert len(session.list_filtered(visible=False)) == 1

    def test_combined_filters(self, make_session):
        session = make_session(n=3)
        session._all_geometries()[0].set_visibility(False)
        visible_cloud_1 = session.list_filtered(visible=True, name="cloud_1")
        assert len(visible_cloud_1) == 1


class TestFilterExtended:

    def test_upper_bound_population(self):
        session = Session(quiet=True)
        for size in [10, 50, 100]:
            g = _geom(size, seed=size)
            session._data.add(g)
            session._order.append(g)
        geoms = session._all_geometries()
        kept, removed, level = session.filter(geoms, "n_points", upper=50)
        assert kept == 2
        assert removed == 1
        assert level == "population"

    def test_both_bounds(self):
        session = Session(quiet=True)
        for size in [10, 50, 100, 200]:
            g = _geom(size, seed=size)
            session._data.add(g)
            session._order.append(g)
        geoms = session._all_geometries()
        kept, removed, level = session.filter(
            geoms,
            "n_points",
            lower=50,
            upper=100,
        )
        assert kept == 2
        assert removed == 2

    def test_filter_stored_vertex_property(self, make_session):
        session = make_session(n=1, n_points=100)
        geoms = session._all_geometries()
        session.measure("height", geoms, store=True)
        heights = geoms[0].vertex_properties.get_property("height")
        median = float(np.median(heights))
        kept, removed, level = session.filter(geoms, "height", upper=median)
        assert level == "point"
        assert kept > 0 and removed > 0

    def test_filter_all_removed(self):
        session = Session(quiet=True)
        g = _geom(10, seed=0)
        session._data.add(g)
        session._order.append(g)
        kept, removed, _ = session.filter([g], "n_points", lower=9999)
        assert removed == 1
        assert kept == 0
        assert len(session._all_geometries()) == 0

    def test_include_categorical_strings(self):
        session = Session(quiet=True)
        g = _geom(20, seed=0)
        labels = np.array(["a", "b", "a", "b", "c"] * 4, dtype=object)
        g.vertex_properties.set_property("label", labels)
        session._data.add(g)
        session._order.append(g)
        kept, removed, level = session.filter([g], "label", include=["a", "c"])
        assert level == "point"
        assert kept == 12  # 8 'a' + 4 'c'
        assert removed == 8
        labels_after = g.vertex_properties.get_property("label")
        assert labels_after is not None
        assert set(labels_after.tolist()) == {"a", "c"}

    def test_exclude_categorical_strings(self):
        session = Session(quiet=True)
        g = _geom(20, seed=0)
        labels = np.array(["a", "b", "a", "b", "c"] * 4, dtype=object)
        g.vertex_properties.set_property("label", labels)
        session._data.add(g)
        session._order.append(g)
        kept, removed, _ = session.filter([g], "label", exclude=["b"])
        assert kept == 12
        assert removed == 8
        labels_after = g.vertex_properties.get_property("label")
        assert labels_after is not None
        assert "b" not in labels_after.tolist()

    def test_include_integer_labels(self):
        session = Session(quiet=True)
        g = _geom(15, seed=0)
        ids = np.array([0, 1, 2] * 5, dtype=np.int32)
        g.vertex_properties.set_property("cluster_id", ids)
        session._data.add(g)
        session._order.append(g)
        kept, removed, _ = session.filter([g], "cluster_id", include=[1, 2])
        assert kept == 10
        assert removed == 5

    def test_include_scalar_single_value(self):
        session = Session(quiet=True)
        g = _geom(10, seed=0)
        g.vertex_properties.set_property("tag", np.array(["x"] * 10, dtype=object))
        session._data.add(g)
        session._order.append(g)
        kept, removed, _ = session.filter([g], "tag", include="x")
        assert kept == 10
        assert removed == 0

    def test_range_and_membership_combined(self):
        session = Session(quiet=True)
        g = _geom(12, seed=0)
        values = np.array([1.0, 2.0, 3.0, 4.0] * 3, dtype=np.float32)
        g.vertex_properties.set_property("v", values)
        session._data.add(g)
        session._order.append(g)
        kept, removed, _ = session.filter(
            [g],
            "v",
            lower=2.0,
            upper=4.0,
            exclude=[3.0],
        )
        assert kept == 6  # values 2.0 and 4.0
        assert removed == 6

    def test_range_on_non_numeric_raises(self):
        session = Session(quiet=True)
        g = _geom(5, seed=0)
        g.vertex_properties.set_property(
            "label", np.array(["a", "b", "c", "a", "b"], dtype=object)
        )
        session._data.add(g)
        session._order.append(g)
        with pytest.raises(TypeError, match="non-numeric"):
            session.filter([g], "label", lower=0.0)

    def test_membership_population_scalar(self):
        session = Session(quiet=True)
        sizes = [10, 20, 30]
        geoms = []
        for size in sizes:
            g = _geom(size, seed=size)
            session._data.add(g)
            session._order.append(g)
            geoms.append(g)
        kept, removed, level = session.filter(geoms, "n_points", include=[10, 30])
        assert level == "population"
        assert kept == 2
        assert removed == 1


class TestOpenFile:

    def test_open_xyz(self, tmp_path):
        path = tmp_path / "test.xyz"
        pts = np.random.RandomState(0).rand(25, 3).astype(np.float32) * 100
        np.savetxt(str(path), pts, delimiter=",", header="x,y,z", comments="")

        session = Session(quiet=True)
        indices = session.open(str(path))
        assert len(indices) == 1
        assert session._all_geometries()[0].get_number_of_points() == 25

    def test_open_persist_false(self, tmp_path):
        path = tmp_path / "temp.xyz"
        pts = np.random.RandomState(0).rand(10, 3).astype(np.float32)
        np.savetxt(str(path), pts, delimiter=",", header="x,y,z", comments="")

        session = Session(quiet=True)
        indices = session.open(str(path), persist=False)
        assert indices == []
        assert len(session._all_geometries()) == 0
        assert len(session._last_results) == 1

    def test_open_with_offset_scale(self, tmp_path):
        path = tmp_path / "scaled.xyz"
        pts = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.float32)
        np.savetxt(str(path), pts, delimiter=",", header="x,y,z", comments="")

        session = Session(quiet=True)
        session.open(str(path), scale=2.0, offset=1.0)
        loaded = session._all_geometries()[0].points
        np.testing.assert_allclose(loaded[0], [1, 3, 5], atol=0.1)


class TestSaveLoad:

    def test_save_xyz_roundtrip(self, make_session, tmp_path):
        session = make_session(n=1, n_points=20)
        geoms = session._all_geometries()
        path = str(tmp_path / "export.xyz")
        session.save(geoms, path, format="xyz")
        assert (tmp_path / "export.xyz").exists()

    def test_save_session_pickle_roundtrip(self, make_session, tmp_path):
        session = make_session(n=2, n_points=30)
        session.group(session._all_geometries(), "TestGroup")
        path = str(tmp_path / "session.pickle")
        session.save_session(path)

        loaded = Session(quiet=True)
        loaded.load_session(path)
        assert len(loaded._all_geometries()) == 2

    def test_save_session_mosaic_roundtrip(self, make_session, tmp_path):
        session = make_session(n=2, n_points=30)
        session.metadata["shape"] = np.array([64, 64, 64])
        path = str(tmp_path / "session.mosaic")
        session.save_session(path)

        loaded = Session(quiet=True)
        loaded.load_session(path)
        assert len(loaded._all_geometries()) == 2
        assert loaded.metadata.get("shape") is not None

    def test_load_session_persist_false(self, make_session, tmp_path):
        session = make_session(n=2, n_points=10)
        path = str(tmp_path / "session.pickle")
        session.save_session(path)

        loaded = Session(quiet=True)
        loaded.load_session(path, persist=False)
        assert len(loaded._all_geometries()) == 0
        assert len(loaded._last_results) == 2

    def test_save_infers_format(self, make_session, tmp_path):
        session = make_session(n=1, n_points=15)
        geoms = session._all_geometries()
        path = str(tmp_path / "out.ndjson")
        session.save(geoms, path)
        assert (tmp_path / "out.ndjson").exists()


class TestMergeExtended:

    def test_merge_default_name(self, make_session):
        session = make_session(n=2, n_points=10)
        geoms = session._all_geometries()
        first_name = session._geometry_name(geoms[0], 0)
        merged = session.merge(geoms)
        assert merged._meta["name"] == first_name

    def test_merge_single_geometry(self):
        session = Session(quiet=True)
        g = _geom(10)
        session._data.add(g)
        session._order.append(g)
        merged = session.merge([g])
        assert merged.get_number_of_points() == 10


class TestResolveRange:

    def test_reversed_range(self, make_session):
        session = make_session(n=5)
        result = session.resolve("#3-1")
        assert len(result) == 3

    def test_range_clamped(self, make_session):
        session = make_session(n=3)
        result = session.resolve("#0-99")
        assert len(result) == 3
