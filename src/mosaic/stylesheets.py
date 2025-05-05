from importlib_resources import files

__all__ = [
    "QGroupBox_style",
    "QPushButton_style",
    "QSpinBox_style",
    "QDoubleSpinBox_style",
    "QComboBox_style",
    "QCheckBox_style",
    "QLineEdit_style",
    "QScrollArea_style",
    "HelpLabel_style",
    "QTabBar_style",
    "QListWidget_style",
    "QSlider_style",
    "QMessageBox_style",
    "QProgressBar_style",
]


def _get_resource_path(resource_name):
    """Get the absolute path to a resource in the package.

    Args:
        resource_name (str): Relative path to the resource within the
            package data directory

    Returns:
        str: The absolute path to the resource
    """
    return str(files("mosaic.data").joinpath(f"data/{resource_name}"))


HelpLabel_style = """
    QLabel {
        color: #696c6f;
        font-size: 12px;
        border-top: 0px;
    }
"""

QGroupBox_style = """
    QGroupBox {
        font-weight: 500;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        margin-top: 6px;
        padding-top: 14px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 7px;
        padding: 0px 5px 0px 5px;
    }
    QPushButton:focus {
        outline: none;
    }
"""

QPushButton_style = """
    QPushButton {
        border: 1px solid #cbd5e1;
        border-radius: 4px;
        padding: 6px 12px;
    }
    QPushButton:hover {
        border: 1px solid #cbd5e1;
        background: #1a000000;
    }
    QPushButton:focus {
        outline: none;
    }
"""

QLineEdit_style = """
    QLineEdit {
        border: 1px solid #cbd5e1;
        border-radius: 4px;
        padding: 4px 8px;
        selection-background-color: rgba(99, 102, 241, 0.6);
        background: transparent;
    }
    QLineEdit:focus {
        outline: none;
        border: 1px solid #4f46e5;
    }
    QLineEdit:hover:!focus {
        border: 1px solid #94a3b8;
    }
    QLineEdit:disabled {
        background-color: #f1f5f9;
        color: #94a3b8;
    }
"""

QSpinBox_style = """
    QSpinBox {
        border: 1px solid #cbd5e1;
        border-radius: 4px;
        padding: 4px 8px;
        background-color: transparent;
        selection-background-color: rgba(99, 102, 241, 0.6);
    }
    QSpinBox:focus {
        outline: none;
        border: 1px solid #4f46e5;
    }
    QSpinBox:hover:!focus {
        border: 1px solid #94a3b8;
    }
    QSpinBox:disabled {
        background-color: #f1f5f9;
        color: #94a3b8;
    }
    QSpinBox::up-button, QSpinBox::down-button {
        border: 1px solid #cbd5e1;
        width: 16px;
        background-color: #f8fafc;
    }
    QSpinBox::up-button {
        border-top-right-radius: 3px;
        border-bottom: none;
    }
    QSpinBox::down-button {
        border-bottom-right-radius: 3px;
    }
    QSpinBox::up-button:hover, QSpinBox::down-button:hover {
        background-color: #f1f5f9;
        border-color: #94a3b8;
    }
    QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {
        background-color: #e2e8f0;
    }
"""


QDoubleSpinBox_style = """
    QDoubleSpinBox {
        border: 1px solid #cbd5e1;
        border-radius: 4px;
        padding: 4px 8px;
        background-color: transparent;
        selection-background-color: rgba(99, 102, 241, 0.6);
    }
    QDoubleSpinBox:focus {
        outline: none;
        border: 1px solid #4f46e5;
    }
    QDoubleSpinBox:hover:!focus {
        border: 1px solid #94a3b8;
    }
    QDoubleSpinBox:disabled {
        background-color: #f1f5f9;
        color: #94a3b8;
    }
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
        border: 1px solid #cbd5e1;
        width: 16px;
        background-color: #f8fafc;
    }
    QDoubleSpinBox::up-button {
        border-top-right-radius: 3px;
        border-bottom: none;
    }
    QDoubleSpinBox::down-button {
        border-bottom-right-radius: 3px;
    }
    QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
        background-color: #f1f5f9;
        border-color: #94a3b8;
    }
    QDoubleSpinBox::up-button:pressed, QDoubleSpinBox::down-button:pressed {
        background-color: #e2e8f0;
    }
"""


QComboBox_style = """
    QComboBox {
        border: 1px solid #cbd5e1;
        border-radius: 4px;
        min-height: 27px;
        padding: 0px 8px;
        background: transparent;
        selection-background-color: rgba(99, 102, 241, 0.6);
    }
    QComboBox:focus {
        outline: none;
        border: 1px solid #4f46e5;
    }
    QComboBox:hover:!focus {
        border: 1px solid #94a3b8;
    }
    QComboBox:disabled {
        background-color: #f1f5f9;
        color: #94a3b8;
    }
    QComboBox::drop-down:disabled {
        border: none;
    }
    QComboBox QAbstractItemView {
        border: 1px solid #cbd5e1;
        border-radius: 4px;
        selection-background-color: rgba(99, 102, 241, 0.3);
    }
"""

QCheckBox_style = f"""
    QCheckBox {{
        spacing: 5px;
        background-color: transparent;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border: 1px solid #cbd5e1;
    }}
    QCheckBox::indicator:checked {{
        image: url('{_get_resource_path("checkbox-cross.svg")}')
    }}
"""

QScrollArea_style = """
    QScrollArea {
        border: none;
    }
    QScrollBar:vertical {
        border: none;
        background: #f1f1f1;
        width: 6px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background: #c1c1c1;
        min-height: 20px;
        border-radius: 3px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QScrollBar:horizontal {
        height: 0px;
        background: transparent;
    }
"""

QTabBar_style = """
    QTabBar::tab {
        background: transparent;
        border: 1px solid #cbd5e1;
        border-bottom: none;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        padding: 6px 12px;
        margin-right: 2px;
    }
    QTabBar::tab:selected {
        color: rgba(99, 102, 241, 1.0);
        border-color: rgba(99, 102, 241, 1.0);

    }
    QTabBar::tab:hover:!selected {
        color: #696c6f;
    }
    /* Style for the tab widget itself */
    QTabWidget::pane {
        border: 1px solid #cbd5e1;
        background-color: transparent;
        border-top-right-radius: 6px;
        border-bottom-right-radius: 6px;
        border-bottom-left-radius: 6px;
    }

    /* Style for the tab contents */
    QWidget#scrollContentWidget {
        background-color: transparent;
    }

    /* Make scroll areas transparent */
    QScrollArea {
        background-color: transparent;
        border: none;
    }

"""

QListWidget_style = """
    QListWidget {
        border: none;
        background-color: transparent;
        outline: none;
        padding: 4px 0px;
    }
    QListWidget::item {
        border-radius: 6px;
        margin: 2px 8px;
        font-size: 13px;
    }
    QListWidget::item:hover {
        background-color: rgba(0, 0, 0, 0.10);
    }
    QListWidget::item:selected {
        background-color: rgba(99, 102, 241, 0.3);
        font-weight: 500;
    }
"""

# Left background used to be #4f46e5
QSlider_style = """
    QSlider {
        height: 24px;
    }
    QSlider:disabled {
        opacity: 0.5;
    }
    QSlider::groove:horizontal {
        height: 4px;
        background: #e2e8f0;
        border-radius: 2px;
    }
    QSlider::groove:horizontal:disabled {
        background: #f1f5f9;
    }
    QSlider::handle:horizontal {
        background: #ffffff;
        border: 1px solid #cbd5e1;
        width: 16px;
        height: 16px;
        margin: -6px 0;
        border-radius: 8px;
    }
    QSlider::handle:horizontal:hover {
        border-color: #4f46e5;
    }
    QSlider::handle:horizontal:focus {
        border: 1px solid #4f46e5;
        background: #f9fafb;
    }
    QSlider::handle:horizontal:disabled {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
    }
    QSlider::sub-page:horizontal {
        background: #94a3b8;
        border-radius: 2px;
    }
    QSlider::sub-page:horizontal:disabled {
        background: #cbd5e1;
    }
"""

QMessageBox_style = """
    QMessageBox QLabel {
        color: #334155;
        font-size: 13px;
    }
    QMessageBox QPushButton {
        border: 1px solid #cbd5e1;
        border-radius: 4px;
        padding: 6px 16px;
        min-width: 80px;
    }

    QMessageBox QPushButton:default:hover {
        background-color: #1a000000;
    }
    QMessageBox QCheckBox {
        color: #475569;
        font-size: 12px;
    }
    QMessageBox QTextEdit {
        border: 1px solid #cbd5e1;
        border-radius: 4px;
        padding: 8px;
    }
"""

QProgressBar_style = """
    QProgressBar {
        border: none;
        background-color: #f3f4f6;
        border-radius: 4px;
        height: 8px;
    }
    QProgressBar::chunk {
        background-color: #4f46e5;
        border-radius: 4px;
    }
"""
