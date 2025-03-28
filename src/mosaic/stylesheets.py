__all__ = ["QGroupBox_style", "QPushButton_style", "QScrollArea_style"]

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
