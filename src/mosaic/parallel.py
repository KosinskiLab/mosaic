from functools import wraps
from typing import Callable, Any, Dict

from qtpy.QtGui import QAction
from qtpy.QtWidgets import QMessageBox
from qtpy.QtCore import QObject, Signal, QThread


class TaskWorker(QObject):
    """Worker object that performs the actual task in a background thread."""

    resultReady = Signal(object)
    errorOccurred = Signal(str)

    def __init__(self, func: Callable, *args, **kwargs):
        """Initialize the worker with the function and arguments."""
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def process(self):
        """Execute the function and emit signals based on the result."""
        try:
            result = self.func(*self.args, **self.kwargs)
            self.resultReady.emit(result)
        except Exception as e:
            self.errorOccurred.emit(str(e))


class BackgroundTaskManager(QObject):
    """Manages execution of long-running tasks in background threads."""

    task_started = Signal(str)
    task_completed = Signal(str, object)
    task_failed = Signal(str, str)

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
        self._callbacks: Dict[str, Callable] = {}

        self.task_completed.connect(self._dispatch_callback)
        self.task_failed.connect(self._default_error_handler)

    def _dispatch_callback(self, task_name, result):
        """Dispatch to the appropriate callback for this task."""
        if task_name in self._callbacks:
            callback, instance = self._callbacks.pop(task_name)
            callback(instance, result)

    def _default_error_handler(self, task_name, error):
        """Default handler for task errors."""
        QMessageBox.warning(
            None, "Error", f"An error occurred in {task_name}: {error}."
        )

    def run_task(
        self, name: str, func: Callable, callback=None, instance=None, *args, **kwargs
    ) -> bool:
        """Run a function in a background thread.

        Args:
            name: A unique identifier for the task.
            func: The function to run.
            *args: Positional arguments to pass to the function.
            callback: Optional callback function to call when task completes.
            instance: Instance to pass to the callback.
            **kwargs: Keyword arguments to pass to the function.

        Returns:
            bool: True if the task was started, False if a task with the same name
                 is already running.
        """
        if name in self._active_tasks:
            return False

        if callback is not None:
            self._callbacks[name] = (callback, instance)

        self.task_started.emit(name)

        thread = QThread()
        worker = TaskWorker(func, instance, *args, **kwargs)
        worker.moveToThread(thread)

        thread.started.connect(worker.process)
        worker.resultReady.connect(lambda result: self._handle_completion(name, result))
        worker.errorOccurred.connect(lambda error: self._handle_error(name, error))

        self._active_tasks[name] = thread
        self._workers[name] = worker

        thread.start()

        return True

    def _handle_completion(self, name: str, result: Any):
        self._cleanup_task(name)
        self.task_completed.emit(name, result)

    def _handle_error(self, name: str, error: str):
        self._cleanup_task(name)
        # Also remove any registered callback
        if name in self._callbacks:
            self._callbacks.pop(name)
        self.task_failed.emit(name, error)

    def _cleanup_task(self, name: str):
        if name in self._active_tasks:
            thread = self._active_tasks.pop(name)
            worker = self._workers.pop(name)

            thread.started.disconnect()
            worker.resultReady.disconnect()
            worker.errorOccurred.disconnect()

            worker.deleteLater()
            thread.quit()
            if not thread.wait(1000):
                thread.terminate()
                thread.wait()

    def is_task_running(self, name: str) -> bool:
        return name in self._active_tasks

    def shutdown(self):
        task_names = list(self._active_tasks.keys())
        for name in task_names:
            self._cleanup_task(name)
        self._active_tasks.clear()
        self._callbacks.clear()


def run_in_background(task_name=None, callback=None):
    """Decorator to run a method in the background thread.

    Args:
        task_name: Optional name for the task. If not provided, uses function name.
        callback: Optional callback function to execute when task completes.
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
