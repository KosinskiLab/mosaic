import mmap
import multiprocessing
import signal
import time

from mosaic.watchdog import MemoryWatchdog


def _hold_memory():
    memory = bytearray(2**30)
    for offset in range(0, len(memory), mmap.PAGESIZE):
        memory[offset] = 1
    time.sleep(60)


def test_watchdog_kills_child_above_memory_limit():
    child = multiprocessing.get_context("spawn").Process(target=_hold_memory)
    try:
        with MemoryWatchdog(limit_bytes=300 * 2**20) as watchdog:
            child.start()
            child.join(timeout=5)
            assert child.exitcode == -signal.SIGKILL
        assert watchdog.tripped is True
    finally:
        if child.pid is not None:
            if child.is_alive():
                child.kill()
            child.join()


def _sleep():
    time.sleep(60)


def test_watchdog_kills_only_the_largest_child():
    context = multiprocessing.get_context("spawn")
    small = context.Process(target=_sleep)
    big = context.Process(target=_hold_memory)
    try:
        with MemoryWatchdog(limit_bytes=300 * 2**20):
            small.start()
            big.start()
            big.join(timeout=5)
            assert big.exitcode == -signal.SIGKILL
            assert small.is_alive()
    finally:
        for child in (small, big):
            if child.pid is not None:
                if child.is_alive():
                    child.kill()
                child.join()


def _hold_memory_on_flag(geometry, **kwargs):
    if geometry._meta.get("big"):
        _hold_memory()
    return geometry


def test_memory_trip_fails_only_its_geometry(make_session):
    session = make_session(n=3)
    geometries = session.resolve("*")
    geometries[1]._meta["big"] = True
    with MemoryWatchdog(limit_bytes=800 * 2**20):
        results, errors = session._run_parallel(
            _hold_memory_on_flag, geometries, "hold", workers=1
        )
    assert results[0] is not None and results[2] is not None
    assert results[1] is None
    assert [index for index, _ in errors] == [1]
