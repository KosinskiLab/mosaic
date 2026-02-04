"""
Parallel backend for offloading compute heavy tasks.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import io
import sys
import uuid
import queue
import warnings
import concurrent
import multiprocessing
from enum import Enum
from typing import Callable, Any, Dict, Optional
from dataclasses import dataclass

from .settings import Settings
from qtpy.QtWidgets import QMessageBox
from qtpy.QtCore import QObject, Signal, QTimer


__all__ = ["report_progress", "submit_task", "submit_task_batch"]

# Worker-side globals (set by initializer, used by worker functions)
_worker_queue: Optional[multiprocessing.Queue] = None
_worker_task_id: Optional[str] = None
_original_stdout: Optional[io.TextIOBase] = None
_original_stderr: Optional[io.TextIOBase] = None


class MessageType(Enum):
    """Types of messages sent from workers to the main process."""

    PROGRESS = "progress"
    MESSAGE = "message"
    STDOUT = "stdout"
    STDERR = "stderr"


@dataclass
class WorkerMessage:
    """Message sent from worker to main process via queue."""

    task_id: str
    type: MessageType
    value: Any
    current: Optional[int] = None
    total: Optional[int] = None


class QueueStream(io.TextIOBase):
    """
    A file-like stream that redirects writes to a multiprocessing Queue.

    This allows capturing stdout/stderr from worker processes without
    the instability of direct fd redirection.

    Parameters
    ----------
    queue : multiprocessing.Queue
        Queue to send messages to.
    stream_type : MessageType
        Type of stream (STDOUT or STDERR).
    fallback_stream : io.TextIOBase
        Original stream to also write to (for debugging).
    """

    def __init__(
        self,
        queue: multiprocessing.Queue,
        stream_type: MessageType,
        fallback_stream: io.TextIOBase,
    ):
        super().__init__()
        self._queue = queue
        self._stream_type = stream_type
        self._fallback = fallback_stream
        self._buffer = ""

    def write(self, text: str) -> int:
        if not text:
            return 0

        if self._fallback:
            try:
                self._fallback.write(text)
                self._fallback.flush()
            except Exception:
                pass

        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._send(line + "\n")

        return len(text)

    def _send(self, text: str):
        """Send text to queue, handling task_id lookup."""
        global _worker_task_id
        if _worker_task_id and self._queue:
            try:
                self._queue.put_nowait(
                    WorkerMessage(
                        task_id=_worker_task_id,
                        type=self._stream_type,
                        value=text,
                    )
                )
            except Exception:
                pass

    def flush(self):
        """Flush any remaining buffered content."""
        if self._buffer:
            self._send(self._buffer)
            self._buffer = ""
        if self._fallback:
            try:
                self._fallback.flush()
            except Exception:
                pass

    def readable(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False


def _init_worker_with_queue(progress_queue: multiprocessing.Queue):
    """
    Initialize worker process with progress queue and stdout/stderr capture.

    This is called once when each worker process starts.
    """
    global _worker_queue, _original_stdout, _original_stderr

    _worker_queue = progress_queue

    _original_stdout = sys.stdout
    _original_stderr = sys.stderr

    sys.stdout = QueueStream(progress_queue, MessageType.STDOUT, _original_stdout)
    sys.stderr = QueueStream(progress_queue, MessageType.STDERR, _original_stderr)

    import os

    for var in ("OMP", "OPENBLAS", "MKL", "VECLIB_MAXIMUM", "NUMEXPR"):
        os.environ[f"{var}_NUM_THREADS"] = "1"


def _wrap_task(func, task_id, *args, **kwargs):
    """
    Wrapper that sets task context and captures warnings.

    This runs in the worker process for each task.
    """
    global _worker_task_id

    _worker_task_id = task_id

    try:
        sys.stdout.flush()
        sys.stderr.flush()

        with warnings.catch_warnings(record=True) as warning_list:
            warnings.simplefilter("always")

            result = func(*args, **kwargs)

            warning_msg = ""
            for warning_item in warning_list:
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
    finally:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        _worker_task_id = None


def _default_handler(task_id, task_name, msg, is_warning=False):
    readable_name = task_name.replace("_", " ").title()
    icon = QMessageBox.Icon.Warning if is_warning else QMessageBox.Icon.Critical
    title = "Operation Warning" if is_warning else "Operation Failed"
    text = f"{readable_name} {'Completed with Warnings' if is_warning else 'Failed with Errors'}"

    msg_box = QMessageBox()
    msg_box.setIcon(icon)
    msg_box.setWindowTitle(title)
    msg_box.setText(text)
    msg_box.setInformativeText(str(msg))
    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg_box.exec()


class BackgroundTaskManager(QObject):
    task_queued = Signal(str, str)  # task_id, task_name
    task_started = Signal(str, str)  # task_id, task_name
    task_completed = Signal(str, str, object)  # task_id, task_name, result
    task_failed = Signal(str, str, str)  # task_id, task_name, error
    task_warning = Signal(str, str, str)  # task_id, task_name, warning
    running_tasks = Signal(int)  # count of running tasks

    task_progress = Signal(str, str, float, int, int)  # id, name, progress, cur, total
    task_message = Signal(str, str, str)  # task_id, name, message
    task_output = Signal(str, str, str)  # task_id, stream_type, text

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
        self.batch_limits: Dict[str, int] = {}
        self.batch_running: Dict[str, set] = {}

        # Output accumulation
        self._task_stdout: Dict[str, list] = {}
        self._task_stderr: Dict[str, list] = {}

        self._initialize()

        self.timer = QTimer()
        self.timer.timeout.connect(self._process_tasks)
        self.timer.start(500)

        self.task_failed.connect(lambda *a: _default_handler(*a, is_warning=False))
        self.task_warning.connect(lambda *a: _default_handler(*a, is_warning=True))

    def _initialize(self):
        """Initialize or reinitialize executors."""
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

        # Create manager for shared queue
        self._manager = multiprocessing.Manager()
        self._progress_queue = self._manager.Queue()

        self.executor = concurrent.futures.ProcessPoolExecutor(
            max_workers=int(Settings.rendering.parallel_worker),
            initializer=_init_worker_with_queue,
            initargs=(self._progress_queue,),
        )
        self.executor_pipeline = concurrent.futures.ProcessPoolExecutor(
            mp_context=multiprocessing.get_context("spawn"),
            max_workers=int(Settings.rendering.pipeline_worker),
            max_tasks_per_child=1,
            initializer=_init_worker_with_queue,
            initargs=(self._progress_queue,),
        )

        self.running_tasks.emit(len(self.futures))

    def _shutdown(self):
        """Clean shutdown of executors and queues."""
        self.futures.clear()
        self.task_info.clear()
        self.task_queue.clear()
        self.batch_limits.clear()
        self.batch_running.clear()
        self._task_stdout.clear()
        self._task_stderr.clear()

        try:
            self.executor.shutdown(wait=False, cancel_futures=True)
            self.executor_pipeline.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

        try:
            if hasattr(self, "_manager"):
                self._manager.shutdown()
        except Exception:
            pass

    def _process_tasks(self):
        """Timer callback: process queue, check completed, submit new tasks."""
        self._poll_progress_queue()
        self._check_completed_tasks()
        self._submit_queued_tasks()
        self.running_tasks.emit(len(self.futures))

    def _poll_progress_queue(self):
        """Drain the progress queue and emit appropriate signals."""
        messages_processed = 0
        max_messages_per_tick = 100

        while messages_processed < max_messages_per_tick:
            try:
                msg: WorkerMessage = self._progress_queue.get_nowait()
                messages_processed += 1

                task_id = msg.task_id
                task_info = self.task_info.get(task_id, {})
                task_name = task_info.get("name", "Unknown")

                if msg.type == MessageType.PROGRESS:
                    progress = msg.value
                    if progress is None and msg.total:
                        progress = msg.current / msg.total
                    self.task_progress.emit(
                        task_id,
                        task_name,
                        progress or 0.0,
                        msg.current or 0,
                        msg.total or 0,
                    )

                elif msg.type == MessageType.MESSAGE:
                    self.task_message.emit(task_id, task_name, msg.value)

                elif msg.type in (MessageType.STDOUT, MessageType.STDERR):
                    stream = "stdout" if msg.type == MessageType.STDOUT else "stderr"
                    buffer = (
                        self._task_stdout if stream == "stdout" else self._task_stderr
                    )
                    buffer.setdefault(task_id, []).append(msg.value)
                    self.task_output.emit(task_id, stream, msg.value)

            except queue.Empty:
                break
            except Exception:
                break

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
        """Submit a single task to the queue.

        Parameters
        ----------
        name : str
            Name of the task.
        func : Callable
            Function to execute.
        callback : Callable, optional
            Callback function to execute on completion.
        batch_id : str, optional
            Existing batch ID to add tasks to. If None, creates new batch.
        args: tuple, optional
            Args to pass to func.
        kwargs: dict, optional
            Kwargs to pass to func.
        reuse_worker : bool, optional
            Reuse worker this operation was executed on.
        """
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

        self._task_stdout[task_id] = []
        self._task_stderr[task_id] = []

        if len(self.task_info) > 1000:
            oldest = next(iter(self.task_info))
            self.task_info.pop(oldest, None)

        self.task_queued.emit(task_id, name)
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
        reuse_worker : bool, optional
            Reuse worker this operation was executed on.

        Returns
        -------
        str
            Batch ID for tracking
        """
        if batch_id is None:
            batch_id = str(uuid.uuid4())

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

        self.task_queue = remaining_queue
        for task in tasks_to_submit:
            self._submit_from_queue(task)

    def _submit_from_queue(self, task):
        """Submit a queued task to the executor."""
        task_id = task["task_id"]
        batch_id = task["batch_id"]

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
            _wrap_task,
            task["func"],
            task_id,
            *task["args"],
            **task["kwargs"],
        )
        self.futures[task_id] = future
        self.task_started.emit(task_id, task["name"])

    def _check_completed_tasks(self):
        """Check for completed futures and handle results."""
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
                    task_info["stdout"] = "".join(self._task_stdout.get(task_id, []))
                    task_info["stderr"] = "".join(self._task_stderr.get(task_id, []))

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

                if batch_id is not None and batch_id in self.batch_running:
                    self.batch_running[batch_id].discard(task_id)

                completed_tasks.append(task_id)

        for task_id in completed_tasks:
            _ = self.futures.pop(task_id, None)
            _ = self._task_stdout.pop(task_id, None)
            _ = self._task_stderr.pop(task_id, None)

            if task_id in self.task_info:
                task_info = self.task_info.pop(task_id)
                _keys = ("stdout", "stderr", "status", "name")
                self.task_info[task_id] = {k: task_info.get(k) for k in _keys}

        if executor_broken:
            self._initialize()

    def get_task_output(self, task_id: str) -> Dict[str, str]:
        """
        Get accumulated stdout/stderr for a task.

        Works for both running and completed tasks.

        Parameters
        ----------
        task_id : str
            The task identifier.

        Returns
        -------
        Dict[str, str]
            Dictionary with 'stdout' and 'stderr' keys.
        """
        if task_id in self.task_info:
            info = self.task_info[task_id]
            if "stdout" in info:
                return {"stdout": info["stdout"], "stderr": info.get("stderr", "")}

        return {
            "stdout": "".join(self._task_stdout.get(task_id, [])),
            "stderr": "".join(self._task_stderr.get(task_id, [])),
        }

    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a task if possible.

        Parameters
        ----------
        task_id : str
            The task identifier.

        Returns
        -------
        bool
            True if the task was cancelled, False if it's already running.
        """
        future = self.futures.get(task_id)
        if future is None:
            return False

        cancelled = future.cancel()
        if cancelled and task_id in self.task_info:
            self.task_info[task_id]["status"] = "failed"

        return cancelled

    def clear_finished_tasks(self) -> list:
        """
        Remove finished tasks from tracking.

        Returns
        -------
        list
            List of removed task IDs.
        """
        removed = []
        for task_id in list(self.task_info.keys()):
            status = self.task_info[task_id].get("status")
            if status in ("completed", "failed"):
                self.task_info.pop(task_id, None)
                removed.append(task_id)
        return removed


def submit_task(name, func, callback=None, *args, **kwargs):
    return BackgroundTaskManager.instance().submit_task(
        name, func, callback, args=args, kwargs=kwargs
    )


def submit_task_batch(tasks, max_concurrent=None, batch_id=None, reuse_worker=True):
    return BackgroundTaskManager.instance().submit_task_batch(
        tasks, max_concurrent, batch_id, reuse_worker
    )


def report_progress(
    progress: float = None,
    message: str = None,
    current: int = None,
    total: int = None,
):
    """
    Report progress from within a worker function.

    Parameters
    ----------
    progress : float, optional
        Progress as a fraction (0.0 to 1.0).
    message : str, optional
        Status message to display.
    current : int, optional
        Current step number (alternative to progress fraction).
    total : int, optional
        Total number of steps (used with current).
    """
    global _worker_queue, _worker_task_id

    if not _worker_queue or not _worker_task_id:
        return

    try:
        if message is not None:
            _worker_queue.put_nowait(
                WorkerMessage(
                    task_id=_worker_task_id,
                    type=MessageType.MESSAGE,
                    value=message,
                )
            )

        if progress is not None or current is not None:
            _worker_queue.put_nowait(
                WorkerMessage(
                    task_id=_worker_task_id,
                    type=MessageType.PROGRESS,
                    value=progress,
                    current=current,
                    total=total,
                )
            )
    except Exception:
        pass
