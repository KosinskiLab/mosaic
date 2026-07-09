"""
Integration tests for command dispatch through the REPL.

Exercises the full pipeline: parse_command -> CommandRegistry.dispatch -> Session.

Copyright (c) 2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from mosaic.commands.repl import MosaicREPL
from mosaic.commands.session import Session
from mosaic.commands.parser import parse_command
from mosaic.commands.registry import CommandRegistry
from mosaic.commands.theme import render_to_text as _render


def _dispatch(session, text):
    parsed = parse_command(text)
    assert parsed is not None
    return CommandRegistry.dispatch(session, parsed)


class TestDispatch:

    def test_list_empty(self):
        result = _dispatch(Session(), "list")
        assert "no geometries" in _render(result).lower()

    def test_list_with_data(self, make_session):
        result = _dispatch(make_session(n=2), "list")
        assert "error" not in _render(result).lower()

    def test_info(self, make_session):
        result = _dispatch(make_session(n=1, n_points=42), "info #0")
        text = _render(result)
        assert "42" in text

    def test_visibility(self, make_session):
        session = make_session(n=1)
        geom = session._all_geometries()[0]
        _dispatch(session, "visibility #0 visible=false")
        assert not geom.visible
        _dispatch(session, "visibility #0 visible=true")
        assert geom.visible

    def test_group_ungroup(self, make_session):
        session = make_session(n=1)
        _dispatch(session, "group #0 TestGroup")
        geom = session._all_geometries()[0]
        assert session._geometry_group(geom) == "TestGroup"
        _dispatch(session, "ungroup #0")
        assert session._geometry_group(geom) == ""

    def test_rename_direct(self, make_session):
        session = make_session(n=1)
        _dispatch(session, "rename #0 NewName")
        assert session._all_geometries()[0]._meta["name"] == "NewName"

    def test_rename_substitution(self, make_session):
        session = make_session(n=1)
        _dispatch(session, "rename #0 s/cloud/storm/")
        assert session._all_geometries()[0]._meta["name"] == "storm_0"

    def test_remove(self, make_session):
        session = make_session(n=3)
        _dispatch(session, "remove #1")
        assert len(session._all_geometries()) == 2

    def test_merge(self, make_session):
        session = make_session(n=3, n_points=10)
        result = _dispatch(session, "merge #0 #1")
        assert "merged" in _render(result).lower() or "Merged" in _render(result)
        assert len(session._all_geometries()) == 2

    def test_unknown_command(self):
        result = _dispatch(Session(), "nonexistent_cmd")
        assert "unknown" in _render(result).lower()

    def test_help_smoke(self):
        result = _dispatch(Session(), "help")
        assert result is not None


class TestREPLExecute:

    def test_execute_returns_output(self, make_session):
        repl = MosaicREPL(session=make_session(n=1))
        output = repl.execute("info #0")
        assert output

    def test_execute_logs_command(self, make_session):
        repl = MosaicREPL(session=make_session(n=1))
        repl.execute("list")
        assert "list" in repl.session._log

    def test_execute_comment_is_noop(self):
        repl = MosaicREPL(session=Session())
        assert repl.execute("# comment") == ""

    def test_substitution(self, make_session):
        """$(list format=ids) should inline geometry IDs."""
        repl = MosaicREPL(session=make_session(n=2))
        output = repl.execute("info $(list format=ids)")
        text = _render(output) if not isinstance(output, str) else output
        assert "#0" in text or "cloud_0" in text

    def test_execute_script_text(self, make_session):
        repl = MosaicREPL(session=make_session(n=2))
        script = "visibility #0 visible=false\nlist"
        repl.execute_script_text(script)
        assert len(repl.session._log) == 2


class TestMeasureFilterDispatch:

    def test_measure_n_points(self, make_session):
        session = make_session(n=2, n_points=50)
        result = _dispatch(session, "measure n_points *")
        assert "50" in _render(result)

    def test_measure_store_array(self, make_session):
        session = make_session(n=1, n_points=30)
        _dispatch(session, "measure width #0 store=true")
        stored = session._all_geometries()[0].vertex_properties.get_property("width")
        assert stored is not None and len(stored) == 30

    def test_filter_population(self):
        session = Session(quiet=True)
        from mosaic.geometry import Geometry
        import numpy as np

        for size in range(10, 110, 10):
            g = Geometry(
                points=np.random.RandomState(size).rand(size, 3).astype(np.float32)
            )
            g._meta["name"] = f"g{size}"
            session._data.add(g)
            session._order.append(g)
        _dispatch(session, "filter * property=n_points lower=30")
        remaining = session._all_geometries()
        assert len(remaining) == 8
        for g in remaining:
            assert g.get_number_of_points() >= 30
