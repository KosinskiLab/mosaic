Formats
=======

.. currentmodule:: mosaic.formats

The :mod:`mosaic.formats` module provides file I/O for the geometry, density,
and session formats used throughout Mosaic.  Most user code only needs the
high-level entry points :func:`open_file`, :func:`open_session`, and
:func:`write_session`; the lower-level container types are listed for
completeness.


Reading
~~~~~~~

:func:`open_file` dispatches to the right parser based on the file extension
and returns a :class:`GeometryDataContainer` of one or more entities.

.. autosummary::
   :toctree: rst

   open_file


Writing
~~~~~~~

.. autosummary::
   :toctree: rst

   OrientationsWriter
   write_density


Session Files
~~~~~~~~~~~~~

Mosaic sessions are written in an indexed binary format that bundles the
pickled application state with optional auxiliary sections (thumbnails,
metadata, …).  The helpers below read and write those archives.

.. autosummary::
   :toctree: rst

   is_session_file
   open_session
   write_session
   read_session_index
   read_session_meta
   read_session_section


Streaming
~~~~~~~~~

Helpers for chunked, level-of-detail access to OME-Zarr volumes.

.. autosummary::
   :toctree: rst

   open_omezarr
   ZarrImageSource


Data Containers
~~~~~~~~~~~~~~~

In-memory representations returned by the parsers.  ``GeometryDataContainer``
groups one or more geometry entities, while ``VertexPropertyContainer`` carries
per-vertex scalar fields alongside them.

.. autosummary::
   :toctree: rst
   :nosignatures:

   GeometryDataContainer
   VertexPropertyContainer


Exceptions
~~~~~~~~~~

.. autosummary::
   :toctree: rst
   :nosignatures:

   NotASegmentationError
