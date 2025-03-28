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
