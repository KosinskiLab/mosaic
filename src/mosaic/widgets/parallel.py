from functools import wraps
from qtpy.QtCore import QThread, Signal, QObject


# Signal manager class to handle communication between threads
class TaskSignalManager(QObject):
    progress_signal = Signal(float)
    finished_signal = Signal(object)
    error_signal = Signal(str)


class BackgroundTaskWorker(QThread):
    def __init__(self, func, args, kwargs, signal_manager):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.signal_manager = signal_manager

    def run(self):
        try:
            # Add progress callback to kwargs if not present
            if "progress_callback" not in self.kwargs:
                self.kwargs[
                    "progress_callback"
                ] = self.signal_manager.progress_signal.emit

            # Call the original function
            result = self.func(*self.args, **self.kwargs)

            # Signal completion with result
            self.signal_manager.finished_signal.emit(result)
        except Exception as e:
            # Signal error
            self.signal_manager.error_signal.emit(str(e))


def background_task(show_progress=True):
    """Decorator to run a method in a background thread.

    Args:
        show_progress (bool): Whether to show a progress dialog
    """

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Create signal manager for this task
            signal_manager = TaskSignalManager()

            # Create progress dialog if requested
            progress_dialog = None
            if show_progress and hasattr(self, "window") and callable(self.window):
                from mosaic.dialogs import ProgressDialog

                window = self.window()
                if window:
                    progress_dialog = ProgressDialog([1], "Processing", window)
                    signal_manager.progress_signal.connect(
                        lambda p: progress_dialog.update_progress()
                    )

            # Create the worker thread
            worker = BackgroundTaskWorker(func, (self,) + args, kwargs, signal_manager)

            # Connect signals
            if hasattr(self, "on_task_completed"):
                signal_manager.finished_signal.connect(self.on_task_completed)
            else:
                signal_manager.finished_signal.connect(lambda _: None)

            if hasattr(self, "on_task_error"):
                signal_manager.error_signal.connect(self.on_task_error)
            else:
                signal_manager.error_signal.connect(lambda _: None)

            # Start the worker
            worker.start()

            if not hasattr(self, "_background_workers"):
                self._background_workers = []
            self._background_workers.append(worker)

            return worker

        return wrapper

    return decorator
