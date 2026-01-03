"""
Parallel backend for offloading compute heavy tasks.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import sys
import uuid
import warnings
import concurrent
from io import StringIO
from typing import Callable, Any, Dict

from .settings import Settings
from qtpy.QtWidgets import QMessageBox
from qtpy.QtCore import QObject, Signal, QTimer


def _default_messagebox(task_name: str, msg: str, is_warning: bool = False):
    readable_name = task_name.replace("_", " ").title()

    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Icon.Critical)
    msg_box.setWindowTitle("Operation Failed")
    msg_box.setText(f"{readable_name} Failed with Errors")
    if is_warning:
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle("Operation Warning")
        msg_box.setText(f"{readable_name} Completed with Warnings")

    msg_box.setInformativeText(str(msg))
    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg_box.exec()


def _wrap_warnings(func, *args, **kwargs):
    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always")

        result = func(*args, **kwargs)
        warning_msg = ""
        for warning_item in warning_list:
            if "citation" in str(warning_item.message).lower():
                continue
            if warning_item.category is DeprecationWarning:
                continue
            warning_msg += f"{warning_item.category.__name__}: {warning_item.message}\n"

        return {
            "result": result,
            "warnings": warning_msg.rstrip() if warning_msg else None,
            "stdout": "",
            "stderr": "",
        }


def _default_error_handler(task_id, task_name, error):
    """Default handler for task errors."""
    return _default_messagebox(task_name, error, is_warning=False)


def _default_warning_handler(task_id, task_name, warning):
    """Default handler for task errors."""
    return _default_messagebox(task_name, warning, is_warning=True)


def _init_worker():
    """Initialize worker process with single-threaded BLAS."""
    import os

    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
    os.environ["NUMEXPR_NUM_THREADS"] = "1"


class BackgroundTaskManager(QObject):
    task_started = Signal(str, str)  # task_id, task_name
    task_completed = Signal(str, str, object)  # task_id, task_name, result
    task_failed = Signal(str, str, str)  # task_id, task_name, error
    task_warning = Signal(str, str, str)  # task_id, task_name, warning
    running_tasks = Signal(int)  # running tasks

    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = BackgroundTaskManager()
        return cls._instance

    def __init__(self):
        super().__init__()

        # Task tracking
        self.task_queue: list = []
        self.task_info: Dict[str, Dict[str, Any]] = {}
        self.futures: Dict[str, concurrent.futures.Future] = {}

        # Batch limits
        self.batch_limits: Dict[str, int] = {}  # batch_id -> max_concurrent
        self.batch_running: Dict[str, set] = {}  # batch_id -> set of running task_ids

        self._initialize()

        self.timer = QTimer()
        self.timer.timeout.connect(self._process_tasks)
        self.timer.start(500)

        self.task_failed.connect(_default_error_handler)
        self.task_warning.connect(_default_warning_handler)

    def _initialize(self):
        """Initialize or reinitialize executors"""
        for task_id in list(self.futures.keys()):
            if task_id in self.task_info:
                task_name = self.task_info[task_id]["name"]
                self.task_failed.emit(
                    task_id,
                    task_name,
                    "Task cancelled: executor was broken by worker crash",
                )
            if task_id in self.futures:
                try:
                    self.futures[task_id].cancel()
                except Exception:
                    pass

        self._shutdown()
        self.executor = concurrent.futures.ProcessPoolExecutor(
            max_workers=int(Settings.rendering.parallel_worker),
        )
        self.executor_pipeline = concurrent.futures.ProcessPoolExecutor(
            max_workers=int(Settings.rendering.pipeline_worker),
            max_tasks_per_child=1,
            initializer=_init_worker,
        )

        self.running_tasks.emit(len(self.futures))

    def _shutdown(self):
        self.futures.clear()
        self.task_info.clear()
        self.task_queue.clear()
        self.batch_limits.clear()
        self.batch_running.clear()

        try:
            self.executor.shutdown(wait=False, cancel_futures=True)
            self.executor_pipeline.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

    def submit_task(
        self,
        name: str,
        func: Callable,
        callback: Callable = None,
        batch_id: str = None,
        args: tuple = (),
        kwargs: dict = None,
        reuse_worker: bool = True,
    ) -> str:
        """Submit a single task to the queue"""
        task_id = str(uuid.uuid4())

        self.task_queue.append(
            {
                "task_id": task_id,
                "batch_id": batch_id,
                "name": name,
                "func": func,
                "args": args,
                "kwargs": kwargs or {},
                "callback": callback,
                "reuse_worker": reuse_worker,
            }
        )

        self.task_info[task_id] = {
            "name": name,
            "batch_id": batch_id,
            "status": "queued",
        }

        if len(self.task_info) > 1000:
            self.task_info.pop(0)

        return task_id

    def submit_task_batch(
        self,
        tasks: list,
        max_concurrent: int = None,
        batch_id: str = None,
        reuse_worker: bool = True,
    ) -> str:
        """
        Submit batch of tasks with optional concurrency limit.

        Parameters
        ----------
        tasks : list of dict
            Each dict: {"name": str, "func": callable, "args": tuple,
                       "kwargs": dict, "callback": callable}
        max_concurrent : int, optional
            Max tasks from this batch running simultaneously.
            If None, no limit (uses global worker limit).
        batch_id : str, optional
            Existing batch ID to add tasks to. If None, creates new batch.
        reuse_worker: bool, optional
            Reuse worker this operation was executed on.

        Returns
        -------
        str
            Batch ID for tracking
        """
        if batch_id is None:
            batch_id = str(uuid.uuid4())

        # Always set batch tracking, store max_concurrent (can be None)
        if batch_id not in self.batch_limits:
            self.batch_limits[batch_id] = max_concurrent
            self.batch_running[batch_id] = set()

        for task in tasks:
            self.submit_task(
                name=task.get("name", "Unnamed Task"),
                func=task["func"],
                callback=task.get("callback"),
                batch_id=batch_id,
                args=task.get("args", ()),
                kwargs=task.get("kwargs", {}),
                reuse_worker=reuse_worker,
            )

        return batch_id

    def _process_tasks(self):
        """Timer callback: check completed tasks and submit queued tasks."""
        self._check_completed_tasks()
        self._submit_queued_tasks()
        self.running_tasks.emit(len(self.futures))

    def _submit_queued_tasks(self):
        """Submit queued tasks that respect batch limits."""
        if not self.task_queue:
            return None

        batch_running = {k: len(v) for k, v in self.batch_running.items()}
        tasks_to_submit, remaining_queue = [], []
        for queued_task in self.task_queue:

            can_run = True
            batch_id = queued_task["batch_id"]
            if batch_id is not None and batch_id in self.batch_limits:
                max_concurrent = self.batch_limits[batch_id]

                if max_concurrent is not None:
                    can_run = batch_running[batch_id] < max_concurrent

                batch_running[batch_id] += int(can_run)

            if can_run:
                tasks_to_submit.append(queued_task)
            else:
                remaining_queue.append(queued_task)

        # Avoid the potential race condition by pre-counting batch running
        self.task_queue = remaining_queue
        for task in tasks_to_submit:
            self._submit_from_queue(task)

    def _submit_from_queue(self, task):
        """Submit a queued task to the executor."""
        task_id = task["task_id"]
        batch_id = task["batch_id"]

        # Track batch membership
        if batch_id is not None and batch_id in self.batch_running:
            self.batch_running[batch_id].add(task_id)

        self.task_info[task_id] = {
            "name": task["name"],
            "callback": task["callback"],
            "batch_id": batch_id,
            "status": "running",
        }

        executor = self.executor_pipeline
        if task.get("reuse_worker", True):
            executor = self.executor

        future = executor.submit(
            _wrap_warnings, task["func"], *task["args"], **task["kwargs"]
        )
        self.futures[task_id] = future
        self.task_started.emit(task_id, task["name"])

    def _check_completed_tasks(self):
        """Check for completed futures and handle results"""
        completed_tasks = []
        executor_broken = False

        for task_id, future in self.futures.items():
            if future.done():
                task_info = self.task_info.get(task_id)
                if not task_info:
                    completed_tasks.append(task_id)
                    continue

                task_name = task_info["name"]
                task_info["status"] = "failed"
                batch_id = task_info.get("batch_id")

                try:
                    ret = future.result()

                    result = ret["result"]
                    warnings_msg = ret["warnings"]

                    task_info["status"] = "completed"
                    task_info["stdout"] = ret.get("stdout")
                    task_info["stderr"] = ret.get("stderr")

                    self.task_completed.emit(task_id, task_name, result)

                    if task_info["callback"]:
                        task_info["callback"](result)

                    if warnings_msg is not None:
                        self.task_warning.emit(task_id, task_name, warnings_msg)

                except concurrent.futures.process.BrokenProcessPool as e:
                    error_msg = f"Worker process died unexpectedly: {str(e)}"
                    self.task_failed.emit(task_id, task_name, error_msg)
                    executor_broken = True

                except Exception as e:
                    error_msg = str(e)
                    self.task_failed.emit(task_id, task_name, error_msg)

                # Update batch tracking
                if batch_id is not None and batch_id in self.batch_running:
                    self.batch_running[batch_id].discard(task_id)

                completed_tasks.append(task_id)

        for task_id in completed_tasks:
            _ = self.futures.pop(task_id, None)

            if task_id in self.task_info:
                task_info = self.task_info.pop(task_id)

                # Lets not keep the callbacks
                _keys = ("stdout", "stderr", "status", "name")
                self.task_info[task_id] = {k: task_info.get(k) for k in _keys}

        if executor_broken:
            self._initialize()


def submit_task(name, func, callback=None, *args, **kwargs):
    return BackgroundTaskManager.instance().submit_task(
        name, func, callback, args=args, kwargs=kwargs
    )


def submit_task_batch(tasks, max_concurrent=None, batch_id=None, reuse_worker=True):
    return BackgroundTaskManager.instance().submit_task_batch(
        tasks, max_concurrent, batch_id, reuse_worker
    )
