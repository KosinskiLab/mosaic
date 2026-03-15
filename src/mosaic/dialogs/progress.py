"""
Implements ProgressDialog, showing progress in the status bar.

Copyright (c) 2024 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from qtpy.QtWidgets import QMessageBox


class ProgressDialog:
    def __init__(self, iterable, title="Processing", parent=None):
        from ..widgets.status_indicator import StatusIndicator

        self.total = len(iterable)
        self.iterator = iter(iterable)
        self.current = 0
        self._indicator = StatusIndicator.instance()

        if self._indicator is not None:
            self._indicator.show_progress(title, self.total)

    def update_progress(self, value: int = None):
        """Update progress bar and status label."""
        if value is None:
            value = self.current

        if self._indicator is not None:
            self._indicator.update_progress(value, self.total)

    def __iter__(self):
        return self

    def __next__(self):
        try:
            item = next(self.iterator)
            self.update_progress()
            self.current += 1
            return item
        except StopIteration:
            self.update_progress()
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        if exc_type is not None:
            QMessageBox.warning(None, "Error", str(exc_value))
            return True

    def close(self):
        """Hide the status bar progress."""
        if self._indicator is not None:
            self._indicator.hide_progress()
