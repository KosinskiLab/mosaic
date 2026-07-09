"""
Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import time
import pytest

from mosaic.parallel import BackgroundTaskManager


@pytest.fixture
def fresh_manager(qapp):
    """Fresh BackgroundTaskManager instance. Does not share singleton state."""
    prev = BackgroundTaskManager._instance
    mgr = BackgroundTaskManager()
    mgr.task_failed.disconnect()
    mgr.task_warning.disconnect()
    BackgroundTaskManager._instance = mgr
    yield mgr
    mgr._shutdown()
    BackgroundTaskManager._instance = prev


def _wait_for(predicate, timeout=5.0, interval=0.02):
    from qtpy.QtWidgets import QApplication

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(interval)
    return False


def _square(x):
    return x * x


def test_submit_io_task_runs_and_returns_via_callback(fresh_manager):
    results = []

    task_id = fresh_manager.submit_io_task(
        name="square",
        func=_square,
        callback=lambda r: results.append(r),
        args=(7,),
    )

    assert isinstance(task_id, str)
    assert _wait_for(lambda: results == [49]), f"callback never fired: {results}"


def _cube(x):
    return x * x * x


def test_submit_task_process_backend_still_works(fresh_manager):
    results = []

    fresh_manager.submit_task(
        name="cube",
        func=_cube,
        callback=lambda r: results.append(r),
        args=(3,),
    )

    assert _wait_for(
        lambda: results == [27], timeout=30.0
    ), f"process task never completed: {results}"


def _boom():
    raise RuntimeError("io boom")


def test_submit_io_task_exception_fires_task_failed(fresh_manager, qtbot):
    with qtbot.waitSignal(fresh_manager.task_failed, timeout=3000) as blocker:
        fresh_manager.submit_io_task(name="boom", func=_boom)

    _task_id, task_name, error_msg = blocker.args
    assert task_name == "boom"
    assert "io boom" in error_msg


def _emit_progress_worker(n):
    from mosaic.parallel import report_progress

    for i in range(n):
        report_progress(current=i + 1, total=n, message=f"step {i + 1}")
    return n


def test_report_progress_from_thread_emits_task_progress(fresh_manager, qtbot):
    emitted = []

    def record(task_id, task_name, progress, current, total):
        emitted.append((task_name, progress, current, total))

    fresh_manager.task_progress.connect(record)

    with qtbot.waitSignal(fresh_manager.task_completed, timeout=3000):
        fresh_manager.submit_io_task(
            name="emit5",
            func=_emit_progress_worker,
            args=(5,),
        )

    # We expect at least the five explicit report_progress calls, each with
    # current incrementing from 1 to 5 and total=5.
    currents = [current for (_name, _progress, current, total) in emitted if total == 5]
    assert currents == [1, 2, 3, 4, 5], f"emitted={emitted}"


def test_report_progress_outside_worker_is_noop(fresh_manager):
    # No worker context set. Must not raise.
    from mosaic.parallel import report_progress

    report_progress(current=1, total=10)
    report_progress(message="hello")
    report_progress(progress=0.5)


def _slow_worker(barrier_event, n):
    # Blocks until the test releases barrier_event, then reports progress.
    from mosaic.parallel import report_progress

    barrier_event.wait(timeout=5.0)
    for i in range(n):
        report_progress(current=i + 1, total=n)
    return n


def test_status_indicator_owner_handoff(fresh_manager, qtbot, qapp):
    import threading
    from qtpy.QtWidgets import QMainWindow
    from mosaic.widgets.status_indicator import StatusIndicator

    mw = QMainWindow()
    mw.statusBar()  # force the status bar to exist
    indicator = StatusIndicator(mw)
    indicator.connect_signals()

    release_a = threading.Event()
    release_b = threading.Event()

    try:
        # Submit task A first.
        a = fresh_manager.submit_io_task(
            name="task-A",
            func=_slow_worker,
            args=(release_a, 3),
        )
        # Wait for A to become the active owner.
        assert _wait_for(
            lambda: indicator._active_io_task_id == a
        ), f"A never became active owner; got {indicator._active_io_task_id}"

        # Submit task B — should take over ownership (most-recent-wins).
        b = fresh_manager.submit_io_task(
            name="task-B",
            func=_slow_worker,
            args=(release_b, 3),
        )
        assert _wait_for(
            lambda: indicator._active_io_task_id == b
        ), f"B never took ownership; got {indicator._active_io_task_id}"

        # Let B complete first. Ownership should hand back to A (still running).
        release_b.set()
        assert _wait_for(
            lambda: indicator._active_io_task_id == a
        ), f"handoff to A failed; got {indicator._active_io_task_id}"

        # Let A finish. Ownership should clear.
        release_a.set()
        assert _wait_for(
            lambda: indicator._active_io_task_id is None
        ), f"ownership never cleared; got {indicator._active_io_task_id}"
    finally:
        # Unblock worker threads regardless of assertion outcome so the
        # fresh_manager teardown doesn't race with parked threads.
        release_a.set()
        release_b.set()
        # Stop the status bar's single-shot timer. It is not parented to
        # the QMainWindow, so mw.deleteLater() leaves it alive and it would
        # later fire on a deleted QLabel.
        indicator._task_timer.stop()
        mw.close()
        mw.deleteLater()


def test_status_indicator_ignores_process_tasks(fresh_manager, qtbot, qapp):
    from qtpy.QtWidgets import QMainWindow
    from mosaic.widgets.status_indicator import StatusIndicator

    mw = QMainWindow()
    mw.statusBar()
    indicator = StatusIndicator(mw)
    indicator.connect_signals()

    try:
        with qtbot.waitSignal(fresh_manager.task_completed, timeout=30000):
            fresh_manager.submit_task(
                name="cube-proc",
                func=_cube,
                callback=None,
                args=(4,),
            )

        # Process task must not have taken the center bar.
        assert indicator._active_io_task_id is None
        assert not indicator.progress_bar.isVisible()
    finally:
        # Stop the status bar's single-shot timer so it does not fire on
        # a deleted QLabel in the next test.
        indicator._task_timer.stop()
        mw.close()
        mw.deleteLater()


def _two_args_worker(a, b):
    return a + b


def test_module_level_submit_io_task_accepts_positional_worker_args(
    fresh_manager, qtbot
):
    """Regression: module-level `submit_io_task` must forward positional
    args after `callback` to the worker. This mirrors how call-sites
    (DTS trajectory import, _open_files) invoke the convenience.
    """
    from mosaic.parallel import submit_io_task as submit_io_task_module

    results = []

    with qtbot.waitSignal(fresh_manager.task_completed, timeout=3000):
        submit_io_task_module(
            "add",
            _two_args_worker,
            lambda r: results.append(r),
            3,
            4,
        )

    assert results == [7]
