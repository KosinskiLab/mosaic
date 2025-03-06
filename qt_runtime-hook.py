import os
import sys


def _append_run_path():
    if getattr(sys, "frozen", False):
        pathlist = []

        # Determine the correct paths for Qt plugins
        qt_plugin_path = os.path.join(sys._MEIPASS, "PyQt5", "Qt", "plugins")
        if os.path.exists(qt_plugin_path):
            pathlist.append(qt_plugin_path)

        # Add pymeshlab-specific paths if needed
        pymeshlab_path = os.path.join(sys._MEIPASS, "pymeshlab")
        if os.path.exists(pymeshlab_path):
            pathlist.append(pymeshlab_path)

        for path in pathlist:
            if path not in sys.path:
                sys.path.append(path)


_append_run_path()
