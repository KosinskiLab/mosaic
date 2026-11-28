import os
import signal

import pytest

from mosaic.geometry import Geometry


def _crash_on_flag(geometry, **kwargs):
    if geometry._meta.get("crash"):
        os.kill(os.getpid(), signal.SIGSEGV)
    return geometry


def test_worker_crash_fails_only_its_geometry(make_session):
    session = make_session(n=3)
    geometries = session.resolve("*")
    geometries[1]._meta["crash"] = True

    results, errors = session._run_parallel(
        _crash_on_flag, geometries, "crash_on_flag", workers=1
    )

    assert isinstance(results[0], Geometry)
    assert results[1] is None
    assert isinstance(results[2], Geometry)
    assert [index for index, _ in errors] == [1]
    assert type(errors[0][1]) is RuntimeError


def _fail_on_flag(geometry, **kwargs):
    if geometry._meta.get("fail"):
        raise ValueError("flagged")
    return geometry


def _flagged_session(make_session, monkeypatch, strict):
    from mosaic.operations import GeometryOperations

    monkeypatch.setattr(
        GeometryOperations, "fail_on_flag", _fail_on_flag, raising=False
    )
    session = make_session(n=3)
    session.strict = strict
    geometries = session.resolve("*")
    geometries[1]._meta["fail"] = True
    return session, geometries


def test_strict_session_raises_with_failing_names(make_session, monkeypatch):
    from mosaic.commands.session import StepFailed

    session, geometries = _flagged_session(make_session, monkeypatch, strict=True)
    with pytest.raises(StepFailed) as info:
        session.apply("fail_on_flag", geometries)
    assert info.value.step == "fail_on_flag"
    assert [name for name, _ in info.value.failures] == ["cloud_1"]


def test_lenient_session_keeps_successes(make_session, monkeypatch):
    session, geometries = _flagged_session(make_session, monkeypatch, strict=False)
    with pytest.warns(UserWarning):
        session.apply("fail_on_flag", geometries)
    assert len(session._last_results) == 2
    assert not any(g._meta.get("fail") for g in session._last_results)
