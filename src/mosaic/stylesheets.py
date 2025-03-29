__all__ = [
    "QGroupBox_style",
    "QPushButton_style",
    "QScrollArea_style",
    "HelpLabel_style",
    "QTabBar_style",
    "QListWidget_style",
    "QSlider_style",
    "QMessageBox_style",
]

HelpLabel_style = """
    QLabel{
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
"""

QListWidget_style = """
    QListWidget {
        border: 1px solid #cbd5e1;
        border-radius: 4px;
        outline: none;
        min-height: 200px;
    }
    QListWidget::item {
        border-radius: 6px;
        padding: 4px 8px;
        margin: 2px 4px;
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

QSlider_style = """
    QSlider {
        height: 24px;
    }
    QSlider:disabled {
        opacity: 0.5;
    }
    QSlider::groove:horizontal {
        height: 4px;
        background: #6b7280;
        border-radius: 2px;
    }
    QSlider::groove:horizontal:disabled {
        opacity: 0.5;
        background: #6b7280;
    }
    QSlider::handle:horizontal {
        background: #ffffff;
        border: 2px solid #3b82f6;
        width: 16px;
        height: 16px;
        margin: -6px 0;
        border-radius: 8px;
    }
    QSlider::handle:horizontal:hover {
        background: #2563eb;
        border-color: #2563eb;
    }
    QSlider::handle:horizontal:disabled {
        opacity: 0.5;
        border: 2px solid #6b7280;
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
