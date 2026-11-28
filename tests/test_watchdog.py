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
