import os
import signal

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
