Parallel
========
.. currentmodule:: mosaic.parallel

The `parallel` module provides background task execution capabilities for long-running operations in the Mosaic GUI, ensuring responsive user interface during compute-intensive tasks.

Task Management
~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: rst
   :nosignatures:
   :inherited-members: QObject

   BackgroundTaskManager
   TaskWorker

Core Task Operations
~~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: rst

   BackgroundTaskManager.run_task
   BackgroundTaskManager.is_task_running
   BackgroundTaskManager.shutdown

Decorators
~~~~~~~~~~
.. autosummary::
   :toctree: rst

   run_in_background

Task Worker Operations
~~~~~~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: rst

   TaskWorker.process
   TaskWorker.resultReady
   TaskWorker.errorOccurred