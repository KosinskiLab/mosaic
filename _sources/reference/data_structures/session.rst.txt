Session
=======

.. currentmodule:: mosaic.commands.session

:class:`Session` is the headless workspace that backs both the
``mosaic-pipeline`` CLI and :class:`~mosaic.data.MosaicData`.  It owns two
:class:`~mosaic.container.DataContainer` instances (point clouds and fitted
models), dispatches geometry operations through
:class:`~mosaic.operations.GeometryOperations`, and reads or writes session
archives.

The class is also re-exported at top level as :class:`mosaic.Session` for
scripting use.


Constructor
~~~~~~~~~~~

.. autosummary::
   :toctree: ../rst/
   :nosignatures:

   Session


Target Resolution
~~~~~~~~~~~~~~~~~

The shell and pipeline languages refer to geometries by index specifiers
(``"#3"``, ``"#1-5"``, ``"*"``, ``"@last"``).  These helpers turn specifiers
into concrete :class:`~mosaic.geometry.Geometry` objects.

.. autosummary::
   :toctree: ../rst/

   Session.resolve
   Session.resolve_many


File I/O
~~~~~~~~

.. autosummary::
   :toctree: ../rst/

   Session.open
   Session.save
   Session.save_session
   Session.load_session


Operations
~~~~~~~~~~

Every registered operation in :class:`~mosaic.operations.GeometryOperations`
is dispatched through :meth:`~Session.apply`.  Per-geometry scalar properties
(volume, surface area, ...) are evaluated through :meth:`~Session.measure`.

.. autosummary::
   :toctree: ../rst/

   Session.apply
   Session.measure


Filtering and Queries
~~~~~~~~~~~~~~~~~~~~~

Select geometries by predicate over their measured properties.

.. autosummary::
   :toctree: ../rst/

   Session.filter
   Session.list_filtered


Container Manipulation
~~~~~~~~~~~~~~~~~~~~~~

.. autosummary::
   :toctree: ../rst/

   Session.remove
   Session.merge
   Session.group
   Session.ungroup


Logging
~~~~~~~

.. autosummary::
   :toctree: ../rst/

   Session.log_command
