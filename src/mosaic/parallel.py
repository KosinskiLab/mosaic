"""
Parallel backend for offloading compute heavy tasks.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import uuid
import warnings
import concurrent
from typing import Callable, Any, Dict

from qtpy.QtWidgets import QMessageBox
from qtpy.QtCore import QObject, Signal, QTimer, QThread


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
    """Wrapper function that captures warnings and returns them with the result"""
    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always")

        try:
            result = func(*args, **kwargs)

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

            return {
                "result": result,
                "warnings": warning_msg.rstrip() if warning_msg else None,
            }

        except Exception as e:
            # Re-raise the exception so it's handled by the executor
            raise e


class BatchContext:
    def __init__(self, render_callback, delay: 500):
        self.manager = BackgroundTaskManager.instance()
        self.render_callback = render_callback
        self.task_ids = []

        self._delay = 500

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        QTimer.singleShot(self._delay, self._check_completion)

    def _check_completion(self):
        # Check if all tasks done
        all_done = all(task_id not in self.manager.futures for task_id in self.task_ids)

        if all_done:
            self.render_callback()
        else:
            QTimer.singleShot(self._delay, self._check_completion)

    def submit_task(self, name, func, callback, *args, **kwargs):
        task_id = self.manager.submit_task(name, func, callback, *args, **kwargs)
        self.task_ids.append(task_id)
        return task_id


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

        self.executor = concurrent.futures.ProcessPoolExecutor(
            max_workers=max(2, QThread.idealThreadCount() - 1)
        )

        self.task_info: Dict[str, Dict[str, Any]] = {}
        self.futures: Dict[str, concurrent.futures.Future] = {}

        self.timer = QTimer()
        self.timer.timeout.connect(self._check_completed_tasks)
        self.timer.start(300)

        self.task_failed.connect(self._default_error_handler)
        self.task_warning.connect(self._default_warning_handler)

    def _default_error_handler(self, task_id, task_name, error):
        """Default handler for task errors."""
        return _default_messagebox(task_name, error, is_warning=False)

    def _default_warning_handler(self, task_id, task_name, warning):
        """Default handler for task errors."""
        return _default_messagebox(task_name, warning, is_warning=True)

    def submit_task(
        self, name: str, func: Callable, callback: Callable = None, *args, **kwargs
    ) -> str:
        """Submit a task to the executor"""
        task_id = str(uuid.uuid4())

        self.task_info[task_id] = {"name": name, "callback": callback}

        self.futures[task_id] = self.executor.submit(
            _wrap_warnings, func, *args, **kwargs
        )

        self.task_started.emit(task_id, name)
        self.running_tasks.emit(len(self.futures))
        return task_id

    def _check_completed_tasks(self):
        """Check for completed futures and handle results"""
        completed_tasks = []

        for task_id, future in self.futures.items():
            if future.done():
                task_info = self.task_info[task_id]
                task_name = task_info["name"]

                try:
                    ret = future.result()

                    result = ret["result"]
                    warnings_msg = ret["warnings"]

                    self.task_completed.emit(task_id, task_name, result)

                    if task_info["callback"]:
                        task_info["callback"](result)

                    if warnings_msg is not None:
                        self.task_warning.emit(task_id, task_name, warnings_msg)

                except Exception as e:
                    error_msg = str(e)
                    self.task_failed.emit(task_id, task_name, error_msg)
                completed_tasks.append(task_id)

        for task_id in completed_tasks:
            _ = self.futures.pop(task_id)
            _ = self.task_info.pop(task_id)
            self.running_tasks.emit(len(self.futures))


def submit_task(name, func, callback, *args, **kwargs):
    return BackgroundTaskManager.instance().submit_task(
        name, func, callback, *args, **kwargs
    )
