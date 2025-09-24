"""
Parallel backend for offloading compute heavy tasks.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import uuid
import warnings
from functools import wraps
from collections import deque
from typing import Callable, Any, Dict, Tuple

from qtpy.QtGui import QAction
from qtpy.QtWidgets import QMessageBox
from qtpy.QtCore import QObject, Signal, QThread, Slot


class TaskWorker(QObject):
    """Worker object that performs the actual task in a background thread."""

    resultReady = Signal(object)
    errorOccurred = Signal(str)
    warningOccurred = Signal(str)

    def __init__(self, func: Callable, *args, **kwargs):
        """Initialize the worker with the function and arguments."""
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def process(self):
        """Execute the function and emit signals based on the result."""
        with warnings.catch_warnings(record=True) as warning_list:
            warnings.simplefilter("always")

            try:
                result = self.func(*self.args, **self.kwargs)

            except Exception as e:
                self.errorOccurred.emit(str(e))
                return None

            warning_msg = ""
            for warning_item in warning_list:

                # TODO: Manage citation warnings more rigorously
                if "citation" in str(warning_item.message).lower():
                    continue

                if warning_item.category is DeprecationWarning:
                    continue

                warning_msg += (
                    f"{warning_item.category.__name__}: {warning_item.message}\n"
                )

            if len(warning_msg):
                self.warningOccurred.emit(warning_msg.rstrip())

            self.resultReady.emit(result)


class BackgroundTaskManager(QObject):
    """Manages execution of long-running tasks in background threads."""

    task_started = Signal(str, str)
    task_completed = Signal(str, str, object)
    task_failed = Signal(str, str, str)
    task_warning = Signal(str, str, str)
    task_queued = Signal(str, str, int)

    # Internal signal for thread-safe queue processing
    _process_queue_signal = Signal()

    _instance = None

    @classmethod
    def instance(cls):
        """Get the singleton instance of the task manager."""
        if cls._instance is None:
            cls._instance = BackgroundTaskManager()
        return cls._instance

    def __init__(self):
        """Initialize the task manager."""
        super().__init__()

        self._active_tasks: Dict[str, QThread] = {}
        self._workers: Dict[str, TaskWorker] = {}
        self._callbacks: Dict[str, Tuple[Callable, object]] = {}
        self._task_names: Dict[str, str] = {}

        self.task_completed.connect(self._dispatch_callback)
        self.task_failed.connect(self._default_error_handler)
        self.task_warning.connect(self._default_warning_handler)

        # Queue management
        self._task_queue: deque = deque()
        self._process_queue_signal.connect(self._process_queue_slot)
        self._max_threads = max(2, QThread.idealThreadCount() - 1)

    def _dispatch_callback(self, task_id: str, task_name: str, result):
        """Dispatch to the appropriate callback for this task."""
        if task_id in self._callbacks:
            callback, instance = self._callbacks.pop(task_id)
            callback(instance, result)

    def _default_error_handler(self, task_id: str, task_name: str, error: str):
        """Default handler for task errors."""
        return self._default_messagebox(task_name, error, is_warning=False)

    def _default_warning_handler(self, task_id: str, task_name: str, warning: str):
        """Default handler for task warnings."""
        return self._default_messagebox(task_name, warning, is_warning=True)

    def _default_messagebox(self, task_name: str, msg: str, is_warning: bool = False):
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

    def run_task(
        self,
        name: str,
        func: Callable,
        callback: Callable = None,
        instance: object = None,
        *args,
        **kwargs,
    ):
        """
        Run a function in a background thread, queuing if necessary.

        Parameters
        ----------
        name : str
            Display name for the task (no longer needs to be unique).
        func : callable
            The function to run.
        callback : callable, optional
            Callback function to call when task completes.
        instance : object, optional
            Class instance to pass to the callback.
        *args: optional
            Positional arguments to pass to func.
        **kwargs : optional
            Keyword arguments to pass to func.

        """
        task_id = str(uuid.uuid4())
        self._task_names[task_id] = name

        if callback is not None:
            self._callbacks[task_id] = (callback, instance)

        if len(self._active_tasks) < self._max_threads:
            return self._start_task(task_id, name, func, instance, *args, **kwargs)

        self._task_queue.append((task_id, name, func, instance, args, kwargs))
        queue_position = len(self._task_queue)
        return self.task_queued.emit(task_id, name, queue_position)

    def _start_task(
        self,
        task_id: str,
        task_name: str,
        func: Callable,
        instance: object,
        *args,
        **kwargs,
    ):
        """Start a task immediately in a new thread."""
        self.task_started.emit(task_id, task_name)

        # Wasteful but safer with open3d
        thread = QThread()
        worker = TaskWorker(func, instance, *args, **kwargs)
        worker.moveToThread(thread)

        thread.started.connect(worker.process)
        worker.resultReady.connect(
            lambda result: self._handle_completion(task_id, result)
        )
        worker.errorOccurred.connect(lambda error: self._handle_error(task_id, error))
        worker.warningOccurred.connect(
            lambda warning: self._default_warning_handler(task_id, task_name, warning)
        )

        self._active_tasks[task_id] = thread
        self._workers[task_id] = worker
        return thread.start()

    def _handle_completion(self, task_id: str, result: Any):
        """Handle task completion and trigger queue processing."""
        task_name = self._task_names.get(task_id, "Unknown Task")

        self._cleanup_task(task_id)
        self.task_completed.emit(task_id, task_name, result)
        self._process_queue_signal.emit()

    def _handle_error(self, task_id: str, error: str):
        """Handle task error and trigger queue processing."""
        task_name = self._task_names.get(task_id, "Unknown Task")
        self._cleanup_task(task_id)

        # Also remove any registered callback
        if task_id in self._callbacks:
            self._callbacks.pop(task_id)

        self.task_failed.emit(task_id, task_name, error)
        self._process_queue_signal.emit()

    def _cleanup_task(self, task_id: str):
        """Clean up task resources."""
        if task_id in self._active_tasks:
            thread = self._active_tasks.pop(task_id)
            worker = self._workers.pop(task_id)

            thread.started.disconnect()
            worker.resultReady.disconnect()
            worker.errorOccurred.disconnect()
            worker.warningOccurred.disconnect()

            worker.deleteLater()
            thread.quit()
            if not thread.wait(1000):
                thread.terminate()
                thread.wait()

        # Clean up task name mapping
        if task_id in self._task_names:
            self._task_names.pop(task_id)

    @Slot()
    def _process_queue_slot(self):
        """Process queued tasks safely on the main thread."""
        while len(self._active_tasks) < self._max_threads:
            try:
                task_id, task_name, func, instance, args, kwargs = (
                    self._task_queue.popleft()
                )
                self._start_task(task_id, task_name, func, instance, *args, **kwargs)
            except IndexError:
                # Queue is empty
                break

    def shutdown(self):
        """Shutdown the task manager and clean up all resources."""
        task_ids = list(self._active_tasks.keys())
        for task_id in task_ids:
            self._cleanup_task(task_id)

        self._active_tasks.clear()
        self._callbacks.clear()
        self._task_names.clear()
        self._task_queue.clear()


def run_in_background(task_name: str = None, callback: Callable = None):
    """Decorator to run a method in the background thread.

    Paramters
    ---------
    task_name: str, optional
        Optional name for the task. If not provided, uses function name.
    callback: callable, optional
        Callback function to execute when task completes.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            name = task_name or func.__name__
            args = [x for x in args if not isinstance(x, QAction)]

            return BackgroundTaskManager.instance().run_task(
                name, func, callback, self, *args, **kwargs
            )

        return wrapper

    return decorator
