from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# Collect pymeshlab data files
datas = collect_data_files("pymeshlab")

# Collect pymeshlab dynamic libraries
binaries = collect_dynamic_libs("pymeshlab")

# Add Qt plugins that pymeshlab needs
hiddenimports = [
    "PyQt5.QtCore",
    "PyQt5.QtGui",
    "PyQt5.QtWidgets",
    "PyQt5.QtXml",
]
