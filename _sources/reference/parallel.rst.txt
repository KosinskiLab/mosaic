Parallel
========

.. currentmodule:: mosaic.parallel

The ``parallel`` module provides background task execution capabilities for long-running operations in the Mosaic GUI, ensuring responsive user interface during compute-intensive tasks. It supports both single task submission and batch processing with concurrency limits.


BackgroundTaskManager
~~~~~~~~~~~~~~~~~~~~~

The core class managing task queuing, execution, and result handling. Uses Qt signals for inter-component communication.

.. autosummary::
   :toctree: rst
   :nosignatures:

   BackgroundTaskManager


Signals
-------

The :class:`BackgroundTaskManager` emits the following Qt signals:

``task_started(task_id: str, task_name: str)``
    Emitted when a task begins execution.

``task_completed(task_id: str, task_name: str, result: object)``
    Emitted when a task completes successfully. The ``result`` contains the function's return value.

``task_failed(task_id: str, task_name: str, error: str)``
    Emitted when a task fails with an exception.

``task_warning(task_id: str, task_name: str, warning: str)``
    Emitted when a task completes but produced warnings during execution.

``running_tasks(count: int)``
    Emitted periodically with the current number of running tasks.


Convenience Functions
~~~~~~~~~~~~~~~~~~~~~

Module-level functions that provide easy access to the singleton :class:`BackgroundTaskManager` instance.

.. autosummary::
   :toctree: rst

   submit_task
   submit_task_batch


Usage Example
~~~~~~~~~~~~~

.. code-block:: python

    from mosaic.parallel import submit_task, submit_task_batch

    # Single task
    def expensive_computation(data):
        # Process data...
        return result

    task_id = submit_task(
        "compute_mesh",
        expensive_computation,
        callback=on_result,
        data=my_data
    )

    # Batch of tasks with concurrency limit
    tasks = [
        {"name": "process_1", "func": func, "args": (data1,)},
        {"name": "process_2", "func": func, "args": (data2,)},
        {"name": "process_3", "func": func, "args": (data3,)},
    ]
    batch_id = submit_task_batch(tasks, max_concurrent=2)
