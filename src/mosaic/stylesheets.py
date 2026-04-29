"""
Mosaic stylesheet and theme system.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import sys

from importlib_resources import files

__all__ = [
    "Colors",
    "Typography",
    "switch_theme",
    "build_appstyle",
    "build_qt_palette",
    "build_global_stylesheet",
    "install_macos_titlebar_filter",
]


class Typography:
    """Ratio-based font sizing anchored to the system default."""

    _RATIOS = {
        "DISPLAY": 1.69,
        "BODY": 1.00,
        "LABEL": 0.92,
        "SMALL": 0.85,
        "CAPTION": 0.77,
    }

    # Defaults assume macOS base of 13 px
    DISPLAY: int = 22
    BODY: int = 13
    LABEL: int = 12
    SMALL: int = 11
    CAPTION: int = 10

    @classmethod
    def set_base(cls, pixel_size: int):
        """Recompute every level from *pixel_size* (the BODY anchor)."""
        for name, ratio in cls._RATIOS.items():
            setattr(cls, name, max(1, round(pixel_size * ratio)))


class Colors:
    """Centralized color definitions for the Mosaic application."""

    LIGHT = {
        "SURFACE": "#ffffff",  # Window / title bar
        "PRIMARY": "#6366f1",  # Indigo 500
        "TEXT_PRIMARY": "#18181b",  # Zinc 900
        "TEXT_SECONDARY": "#52525b",  # Zinc 600
        "TEXT_MUTED": "#a1a1aa",  # Zinc 400
        "BORDER_HOVER": "#d4d4d8",  # Zinc 300
        "BORDER_DARK": "#ebebec",  # Subtle border
        "BG_SECONDARY": "#fafafa",  # Surface dim
        "BG_TERTIARY": "#f4f4f5",  # Surface tint (Zinc 100)
        "BG_HOVER": "rgba(0, 0, 0, 0.06)",
        "BG_PRESSED": "rgba(0, 0, 0, 0.10)",
        "SUCCESS": "#10b981",
        "WARNING": "#f59e0b",
        "ERROR": "#ef4444",
    }

    DARK = {
        "SURFACE": "#18181b",  # Zinc 900 — Window / title bar
        "PRIMARY": "#818cf8",  # Indigo 400
        "TEXT_PRIMARY": "#fafafa",  # Zinc 50
        "TEXT_SECONDARY": "#a1a1aa",  # Zinc 400
        "TEXT_MUTED": "#71717a",  # Zinc 500
        "BORDER_HOVER": "#3f3f46",  # Zinc 700
        "BORDER_DARK": "#2e2e33",  # Subtle dark border
        "BG_SECONDARY": "#1e1e22",  # Surface dim
        "BG_TERTIARY": "#27272a",  # Surface tint (Zinc 800)
        "BG_HOVER": "rgba(255, 255, 255, 0.06)",
        "BG_PRESSED": "rgba(255, 255, 255, 0.10)",
        "SUCCESS": "#34d399",
        "WARNING": "#fbbf24",
        "ERROR": "#f87171",
    }

    @classmethod
    def apply_palette(cls, palette: dict):
        """Apply a palette dict, updating all mutable color attributes."""
        for key, value in palette.items():
            setattr(cls, key, value)

        cls.ICON = cls.TEXT_MUTED
        cls.ICON_MUTED = cls.TEXT_MUTED
        cls.ICON_ACTIVE = cls.TEXT_SECONDARY

    @classmethod
    def alpha(cls, token, value):
        """Return a palette color at the given alpha as an rgba() string."""
        import re
        from qtpy.QtGui import QColor

        raw = getattr(cls, token)
        match = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", raw)
        if match:
            r, g, b = match.group(1), match.group(2), match.group(3)
            return f"rgba({r}, {g}, {b}, {value})"
        c = QColor(raw)
        return f"rgba({c.red()}, {c.green()}, {c.blue()}, {value})"

    @classmethod
    def is_dark(cls):
        """Return True if the current palette is dark."""
        return cls.PRIMARY == cls.DARK["PRIMARY"]

    RADIUS = 6  # Standard border radius for controls (px)
    WIDGET_HEIGHT = 30  # Standard height for input widgets (px)

    # Standard coordinate axis colors
    AXIS = ((0.8, 0.2, 0.2), (0.26, 0.65, 0.44), (0.2, 0.4, 0.8))

    ENTITY = [
        (0.18, 0.62, 0.78),  # Cerulean
        (0.98, 0.75, 0.18),  # Saffron
        (0.32, 0.70, 0.40),  # Malachite
        (0.72, 0.32, 0.78),  # Amethyst
        (0.95, 0.50, 0.20),  # Tangerine
        (0.25, 0.20, 0.72),  # Sapphire
        (0.85, 0.35, 0.55),  # Cerise
        (0.55, 0.25, 0.60),  # Plum
        (0.20, 0.68, 0.58),  # Viridian
        (0.92, 0.58, 0.45),  # Coral
        (0.35, 0.35, 0.75),  # Ultramarine
        (0.75, 0.72, 0.25),  # Olive gold
        (0.25, 0.78, 0.72),  # Turquoise
        (0.65, 0.45, 0.20),  # Bronze
        (0.52, 0.58, 0.85),  # Periwinkle
        (0.88, 0.40, 0.70),  # Fuchsia
        (0.38, 0.58, 0.28),  # Moss
        (0.70, 0.55, 0.65),  # Mauve
        (0.28, 0.55, 0.45),  # Teal
        (0.82, 0.65, 0.55),  # Peach
        (0.48, 0.38, 0.55),  # Grape
        (0.80, 0.42, 0.30),  # Terracotta
    ]

    ANNOTATION = [tuple(min(1.0, c + 0.5) for c in color) for color in ENTITY]

    CATEGORY = {
        # Pipeline operation categories
        "input": "#6366f1",  # Indigo
        "preprocessing": "#3b82f6",  # Blue
        "parametrization": "#10b981",  # Emerald
        "analysis": "#06b6d4",  # Cyan
        "export": "#f97316",  # Orange
        # Animation types
        "trajectory": "#3b82f6",  # Blue
        "camera": "#10b981",  # Emerald
        "zoom": "#14b8a6",  # Teal
        "volume": "#eab308",  # Yellow
        "visibility": "#8b5cf6",  # Violet
        "waypoint": "#ec4899",  # Pink
    }


# Initialize class attributes from LIGHT palette at import time
Colors.apply_palette(Colors.LIGHT)


def _get_resource_path(resource_name):
    """Get the absolute path to a resource in the package."""
    return str(files("mosaic.data").joinpath(f"data/{resource_name}"))


def _build_QGroupBox_style():
    return f"""
    QGroupBox {{
        font-weight: 600;
        border: none;
        border-bottom: 1px solid {Colors.BORDER_DARK};
        border-radius: 0px;
        margin-bottom: 4px;
        padding-top: 14px;
        padding-bottom: 10px;
    }}
    QGroupBox::title {{
        subcontrol-origin: padding;
        left: 0px;
        color: {Colors.TEXT_MUTED};
    }}
"""


def _build_QPushButton_style():
    return f"""
    QPushButton {{
        border: 1px solid {Colors.BORDER_DARK};
        border-radius: {Colors.RADIUS}px;
        padding: 6px 12px;
    }}
    QPushButton:hover {{
        background: {Colors.BG_HOVER};
        border: 1px solid {Colors.BORDER_HOVER};
    }}
    QPushButton:pressed {{
        background: {Colors.BG_PRESSED};
        border: 1px solid {Colors.BORDER_HOVER};
    }}
    QPushButton:focus {{
        outline: none;
    }}
    QPushButton:disabled {{
        color: {Colors.BORDER_HOVER};
    }}
"""


def _build_QLineEdit_style():
    return f"""
    QLineEdit {{
        border: 1px solid {Colors.BORDER_DARK};
        border-radius: {Colors.RADIUS}px;
        padding: 6px 8px;
        selection-background-color: {Colors.alpha("PRIMARY", 0.6)};
    }}
    QLineEdit:focus {{
        border: 1px solid {Colors.BORDER_HOVER};
    }}
    QLineEdit:hover:!focus {{
        border: 1px solid {Colors.BORDER_HOVER};
    }}
    QLineEdit:disabled {{
        color: {Colors.BORDER_HOVER};
    }}
"""


def _build_QSpinBox_style():
    return f"""
    QSpinBox, QDoubleSpinBox {{
        border: 1px solid {Colors.BORDER_DARK};
        border-radius: {Colors.RADIUS}px;
        padding: 6px 8px;
        background: transparent;
        selection-background-color: {Colors.alpha("PRIMARY", 0.6)};
    }}
    QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {Colors.BORDER_HOVER};
    }}
    QSpinBox:hover:!focus, QDoubleSpinBox:hover:!focus {{
        border: 1px solid {Colors.BORDER_HOVER};
    }}
    QSpinBox:disabled, QDoubleSpinBox:disabled {{
        color: {Colors.BORDER_HOVER};
    }}
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        border: 1px solid {Colors.BORDER_DARK};
        width: 16px;
        background-color: {Colors.BG_SECONDARY};
    }}
    QSpinBox::up-button, QDoubleSpinBox::up-button {{
        border-top-right-radius: {Colors.RADIUS - 1}px;
        border-bottom: none;
    }}
    QSpinBox::down-button, QDoubleSpinBox::down-button {{
        border-bottom-right-radius: {Colors.RADIUS - 1}px;
    }}
    QSpinBox::up-button:hover, QSpinBox::down-button:hover,
    QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
        background-color: {Colors.BG_TERTIARY};
        border-color: {Colors.BORDER_HOVER};
    }}
    QSpinBox::up-button:pressed, QSpinBox::down-button:pressed,
    QDoubleSpinBox::up-button:pressed, QDoubleSpinBox::down-button:pressed {{
        background-color: {Colors.BORDER_DARK};
    }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
        image: url('{_get_resource_path("spinbox-caret-up.svg")}');
        width: 10px;
        height: 10px;
    }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
        image: url('{_get_resource_path("spinbox-caret-down.svg")}');
        width: 10px;
        height: 10px;
    }}
"""


def _build_QComboBox_style():
    return f"""
    QComboBox {{
        border: 1px solid {Colors.BORDER_DARK};
        border-radius: {Colors.RADIUS}px;
        min-height: {Colors.WIDGET_HEIGHT - 2}px;
        padding: 0px 8px;
        background: transparent;
        selection-background-color: {Colors.alpha("PRIMARY", 0.6)};
    }}
    QComboBox:focus {{
        outline: none;
        border: 1px solid {Colors.BORDER_HOVER};
    }}
    QComboBox:hover:!focus {{
        border: 1px solid {Colors.BORDER_HOVER};
    }}
    QComboBox:disabled {{
        color: {Colors.BORDER_HOVER};
    }}
    QComboBox::down-arrow {{
        image: url('{_get_resource_path("spinbox-caret-down.svg")}');
        width: 10px;
        height: 10px;
    }}
"""


def _build_QCheckBox_style():
    return f"""
    QCheckBox {{
        spacing: 5px;
        background-color: transparent;
        outline: none;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border: 1px solid {Colors.BORDER_DARK};
        background-color: transparent;
    }}
    QCheckBox::indicator:focus {{
        border: 1px solid {Colors.BORDER_HOVER};
    }}
    QCheckBox::indicator:hover:!focus {{
        border: 1px solid {Colors.BORDER_HOVER};
    }}
    QCheckBox::indicator:pressed {{
        background-color: transparent;
    }}
    QCheckBox::indicator:checked {{
        background-color: transparent;
        image: url('{_get_resource_path("checkbox-checkmark.svg")}')
    }}
"""


def _build_QScrollArea_style():
    return f"""
    QScrollArea {{
        border: none;
    }}
    QScrollBar:vertical {{
        border: none;
        background: {Colors.BG_TERTIARY};
        width: 6px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {Colors.BORDER_DARK};
        min-height: 20px;
        border-radius: 3px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        height: 0px;
        background: transparent;
    }}
"""


def _build_QTable_style():
    return f"""
    QTableWidget {{
        border: 1px solid {Colors.BORDER_DARK};
        border-radius: {Colors.RADIUS}px;
        background-color: transparent;
        outline: none;
        gridline-color: {Colors.BORDER_DARK};
        selection-background-color: {Colors.alpha("PRIMARY", 0.07)};
        selection-color: {Colors.PRIMARY};
    }}
    QTableWidget::item {{
        border: none;
    }}
    QTableWidget::item:hover {{
        background-color: {Colors.alpha("BG_HOVER", 0.03)};
    }}
    QTableWidget QHeaderView::section {{
        background: transparent;
        border: none;
        border-bottom: 1px solid {Colors.BORDER_DARK};
        padding: 4px 4px;
        color: {Colors.TEXT_SECONDARY};
    }}
    QTableWidget QTableCornerButton::section {{
        background: transparent;
        border: none;
        border-bottom: 1px solid {Colors.BORDER_DARK};
    }}
"""


def _build_QToolTip_style():
    return f"""
    QToolTip {{
        background: {Colors.SURFACE};
        color: {Colors.TEXT_PRIMARY};
        padding: 2px 2px;
        font-size: {Typography.SMALL}px;
        border: none;
    }}
"""


def _build_QListWidget_style():
    return f"""
    QListWidget, QTreeWidget {{
        border: none;
        background-color: transparent;
        outline: none;
        padding: 4px 0px;
        font-size: {Typography.BODY}px;
        selection-background-color: {Colors.alpha("PRIMARY", 0.3)};
        selection-color: {Colors.PRIMARY};
    }}
    QTreeWidget {{
        selection-background-color: transparent;
        selection-color: {Colors.TEXT_PRIMARY};
    }}
    QListWidget::item, QTreeWidget::item {{
        border-radius: {Colors.RADIUS}px;
        border: none;
        padding: 4px 0px;
        margin: 2px 0px;
        outline: none;
    }}
    QTreeWidget::item:hover, QTreeWidget::item:selected {{
        background-color: rgba(0, 0, 0, 0.0);
    }}
    QListWidget::item:hover {{
        background-color: {Colors.BG_PRESSED};
    }}
    QListWidget::item:selected {{
        font-weight: 500;
    }}
"""


def _build_QSlider_style():
    return f"""
    QSlider {{
        height: 24px;
    }}
    QSlider:disabled {{
        opacity: 0.5;
    }}
    QSlider::groove:horizontal {{
        height: 4px;
        background: {Colors.BORDER_DARK};
        border-radius: 2px;
    }}
    QSlider::groove:horizontal:disabled {{
        background: {Colors.BG_TERTIARY};
    }}
    QSlider::handle:horizontal {{
        background: {Colors.SURFACE};
        border: 1px solid {Colors.BORDER_DARK};
        width: 16px;
        height: 16px;
        margin: -6px 0;
        border-radius: 8px;
    }}
    QSlider::handle:horizontal:hover {{
        border-color: {Colors.BORDER_HOVER};
    }}
    QSlider::handle:horizontal:hover:!focus {{
        border-color: {Colors.BORDER_HOVER};
    }}
    QSlider::handle:horizontal:disabled {{
        background: {Colors.BG_SECONDARY};
        border: 1px solid {Colors.BORDER_DARK};
    }}
    QSlider::sub-page:horizontal {{
        background: {Colors.BORDER_HOVER};
        border-radius: 2px;
    }}
    QSlider::sub-page:horizontal:disabled {{
        background: {Colors.BORDER_DARK};
    }}
"""


def _build_QMessageBox_style():
    return f"""
    QMessageBox {{
        background-color: {Colors.SURFACE};
        color: {Colors.TEXT_PRIMARY};
    }}
    QMessageBox QLabel {{
        font-size: {Typography.BODY}px;
    }}
    QMessageBox QPushButton {{
        border: 1px solid {Colors.BORDER_DARK};
        border-radius: {Colors.RADIUS}px;
        padding: 6px 16px;
        min-width: 80px;
    }}
    QMessageBox QPushButton:hover {{
        border: 1px solid {Colors.ICON_MUTED};
        background: {Colors.BG_HOVER};
    }}
    QMessageBox QPushButton:pressed {{
        border: 1px solid {Colors.ICON_MUTED};
        background: {Colors.BG_PRESSED};
    }}
    QMessageBox QPushButton:focus {{
        outline: none;
    }}
    QMessageBox QCheckBox {{
        color: {Colors.TEXT_PRIMARY};
        font-size: {Typography.LABEL}px;
    }}
    QMessageBox QTextEdit {{
        border: 1px solid {Colors.BORDER_DARK};
        border-radius: {Colors.RADIUS}px;
        padding: 8px;
    }}
"""


def _build_QToolButton_style():
    return f"""
    QToolButton {{
        padding: 4px 6px;
        border-radius: {Colors.RADIUS}px;
        font-size: {Typography.SMALL}px;
        background: transparent;
        border: 1px solid transparent;
    }}
    QToolButton:hover {{
        background: {Colors.BG_HOVER};
        border: 1px solid {Colors.BORDER_DARK};
    }}
    QToolButton:pressed {{
        background: {Colors.BG_PRESSED};
        border: 1px solid {Colors.BORDER_HOVER};
    }}
    QToolButton::menu-indicator {{
        image: url(none);
        width: 0px;
        subcontrol-position: right bottom;
        subcontrol-origin: padding;
        margin-left: 0px;
    }}
    QToolButton::menu-button {{
        border: 1px solid transparent;
        width: 14px;
        padding: 0px;
        margin: 0px;
        border-radius: 4px;
    }}
    QToolButton::menu-button:hover {{
        background: {Colors.BG_HOVER};
    }}
"""


def _build_QMenu_style():
    return f"""
    QMenu {{
        background-color: {Colors.SURFACE};
        border: 1px solid {Colors.BORDER_DARK};
        border-radius: {Colors.RADIUS}px;
        padding: 4px;
    }}
    QMenu::item {{
        padding: 4px 12px;
        border-radius: 4px;
        border: 1px solid transparent;
    }}
    QMenu::item:selected {{
        background: {Colors.BG_HOVER};
        border: 1px solid {Colors.BORDER_DARK};
    }}
    QMenu::item:pressed {{
        background: {Colors.BG_PRESSED};
        border: 1px solid {Colors.BORDER_HOVER};
    }}
    QMenu::separator {{
        height: 1px;
        background-color: {Colors.BG_PRESSED};
        margin: 4px 8px;
    }}
    QMenu::indicator {{
        width: 16px;
        height: 16px;
        margin-right: 6px;
        background-color: transparent;
    }}
    QMenu::indicator:checked {{
        background-color: transparent;
        image: url('{_get_resource_path("checkbox-checkmark.svg")}');
    }}
"""


def _build_QDockWidget_style():
    return f"""
    QDockWidget {{
        titlebar-close-icon: url('{_get_resource_path("dock-close.svg")}');
        titlebar-normal-icon: url('{_get_resource_path("dock-float.svg")}');
        margin: 0px;
        padding: 0px;
    }}
    QDockWidget::title {{
        background: transparent;
        text-align: left;
        padding-top: 2px;
    }}
    QDockWidget::close-button, QDockWidget::float-button {{
        border: 1px solid {Colors.BORDER_DARK};
        background: transparent;
        width: 24px;
        height: 24px;
        max-width: 24px;
        max-height: 24px;
        border-radius: 4px;
        subcontrol-origin: padding;
    }}
    QDockWidget::close-button {{
        subcontrol-position: right center;
        right: 4px;
    }}
    QDockWidget::float-button {{
        subcontrol-position: right center;
        right: 24px;
    }}
    QDockWidget::close-button:hover, QDockWidget::float-button:hover {{
        background: {Colors.BG_HOVER};
        border: 1px solid {Colors.BORDER_DARK};
    }}
    QDockWidget::close-button:pressed, QDockWidget::float-button:pressed {{
        background: {Colors.BG_PRESSED};
        border: 1px solid {Colors.BORDER_HOVER};
    }}
    QMainWindow::separator {{
        width: 4px;
        height: 4px;
        background: transparent;
    }}
"""


# This is used by the main application to achieve consistent styling
_GLOBAL_STYLES = [
    _build_QMessageBox_style,
    _build_QPushButton_style,
    _build_QLineEdit_style,
    _build_QSpinBox_style,
    _build_QComboBox_style,
    _build_QCheckBox_style,
    _build_QSlider_style,
    _build_QGroupBox_style,
    _build_QListWidget_style,
    _build_QScrollArea_style,
    _build_QToolButton_style,
    _build_QMenu_style,
    _build_QDockWidget_style,
    _build_QTable_style,
    _build_QToolTip_style,
]


def build_global_stylesheet():
    """Build the concatenated global stylesheet from current Colors values."""
    return "".join(fn() for fn in _GLOBAL_STYLES)


def build_qt_palette():
    """Build a QPalette from the current Colors values."""
    from qtpy.QtGui import QColor, QPalette

    pal = QPalette()
    surface = Colors.SURFACE

    pal.setColor(QPalette.ColorRole.Window, QColor(surface))
    pal.setColor(QPalette.ColorRole.Base, QColor(surface))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(Colors.BG_TERTIARY))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(Colors.TEXT_PRIMARY))
    pal.setColor(QPalette.ColorRole.Text, QColor(Colors.TEXT_PRIMARY))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(Colors.TEXT_MUTED))
    pal.setColor(QPalette.ColorRole.Button, QColor(surface))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(Colors.TEXT_PRIMARY))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(Colors.PRIMARY))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    return pal


def _get_nswindow(widget):
    """Return the NSWindow pointer for a Qt widget, or None."""
    if sys.platform != "darwin":
        return None
    try:
        import ctypes
        import ctypes.util

        lib_path = ctypes.util.find_library("objc")
        if not lib_path:
            return None
        objc = ctypes.cdll.LoadLibrary(lib_path)
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        send = objc.objc_msgSend
        send.restype = ctypes.c_void_p
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        return send(int(widget.winId()), objc.sel_registerName(b"window"))
    except Exception:
        return None


def _apply_macos_titlebar(ns_win, hide_title=False):
    """Make a native window's title bar transparent with themed background.

    Parameters
    ----------
    hide_title : bool, optional
        Content view extends behind the title bar, e.g., make tab bar sit
        alongside traffic lights.
    """
    try:
        import ctypes
        import ctypes.util

        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        send = objc.objc_msgSend

        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
        send.restype = ctypes.c_void_p
        send(ns_win, objc.sel_registerName(b"setTitlebarAppearsTransparent:"), True)

        if hide_title:
            send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
            send.restype = ctypes.c_void_p
            send(ns_win, objc.sel_registerName(b"setTitleVisibility:"), 1)

            # Extend content behind the title bar
            send.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            send.restype = ctypes.c_ulong
            mask = send(ns_win, objc.sel_registerName(b"styleMask"))
            mask |= 1 << 15  # NSWindowStyleMaskFullSizeContentView
            send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
            send.restype = ctypes.c_void_p
            send(ns_win, objc.sel_registerName(b"setStyleMask:"), mask)

            # Invisible toolbar so macOS enlarges the title bar region and
            # vertically centers the traffic lights with the tab bar.
            NSToolbar = objc.objc_getClass(b"NSToolbar")
            send.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            send.restype = ctypes.c_void_p
            toolbar = send(NSToolbar, objc.sel_registerName(b"alloc"))

            NSString = objc.objc_getClass(b"NSString")
            send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p]
            send.restype = ctypes.c_void_p
            tb_id = send(
                NSString,
                objc.sel_registerName(b"stringWithUTF8String:"),
                b"mosaic",
            )
            send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
            send.restype = ctypes.c_void_p
            toolbar = send(
                toolbar, objc.sel_registerName(b"initWithIdentifier:"), tb_id
            )
            send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
            send.restype = ctypes.c_void_p
            send(
                toolbar,
                objc.sel_registerName(b"setShowsBaselineSeparator:"),
                False,
            )
            send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
            send.restype = ctypes.c_void_p
            send(ns_win, objc.sel_registerName(b"setToolbar:"), toolbar)

            # Unified compact style — minimal height increase
            send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
            send.restype = ctypes.c_void_p
            send(ns_win, objc.sel_registerName(b"setToolbarStyle:"), 4)

            # Hide the toolbar separator line
            send(ns_win, objc.sel_registerName(b"setTitlebarSeparatorStyle:"), 0)

            # Allow dragging the window by any non-interactive background
            send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
            send.restype = ctypes.c_void_p
            send(
                ns_win,
                objc.sel_registerName(b"setMovableByWindowBackground:"),
                True,
            )

        _update_macos_titlebar_color(ns_win)
    except Exception:
        pass


def _update_macos_titlebar_color(ns_win):
    """Set an NSWindow's background color to match the current theme surface."""
    try:
        import ctypes
        import ctypes.util
        from qtpy.QtGui import QColor

        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        send = objc.objc_msgSend

        c = QColor(Colors.SURFACE)
        NSColor = objc.objc_getClass(b"NSColor")
        send.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
        ]
        send.restype = ctypes.c_void_p
        color = send(
            NSColor,
            objc.sel_registerName(b"colorWithRed:green:blue:alpha:"),
            c.redF(),
            c.greenF(),
            c.blueF(),
            1.0,
        )
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        send.restype = ctypes.c_void_p
        send(ns_win, objc.sel_registerName(b"setBackgroundColor:"), color)

        # Match NSWindow appearance to the theme
        appearance_name = (
            b"NSAppearanceNameDarkAqua"
            if c.lightness() < 128
            else b"NSAppearanceNameAqua"
        )
        NSString = objc.objc_getClass(b"NSString")
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p]
        send.restype = ctypes.c_void_p
        ns_name = send(
            NSString, objc.sel_registerName(b"stringWithUTF8String:"), appearance_name
        )
        NSAppearance = objc.objc_getClass(b"NSAppearance")
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        send.restype = ctypes.c_void_p
        appearance = send(
            NSAppearance, objc.sel_registerName(b"appearanceNamed:"), ns_name
        )
        if appearance:
            send(ns_win, objc.sel_registerName(b"setAppearance:"), appearance)
    except Exception:
        pass


def install_macos_titlebar_filter():
    """Install an application-wide event filter for native title bar styling."""
    if sys.platform != "darwin":
        return None

    from qtpy.QtWidgets import QApplication
    from qtpy.QtCore import QEvent, QObject

    class _MacOSTitleBarFilter(QObject):
        """Event filter that styles the native title bar of every top-level window."""

        def eventFilter(self, obj, event):
            if (
                event.type() == QEvent.Type.Show
                and hasattr(obj, "isWindow")
                and obj.isWindow()
            ):
                from qtpy.QtWidgets import QMainWindow

                if isinstance(obj, QMainWindow):
                    return False
                ns_win = _get_nswindow(obj)
                if ns_win is not None:
                    _apply_macos_titlebar(ns_win)
            return False

    app = QApplication.instance()
    if app is not None:
        app.installEventFilter(_MacOSTitleBarFilter(app))


def build_appstyle():

    from qtpy.QtWidgets import QProxyStyle, QComboBox, QMenu

    class MosaicStyle(QProxyStyle):
        def __init__(self):
            super().__init__("Fusion")

        def polish(self, obj):
            from qtpy.QtGui import QPalette

            if isinstance(obj, QPalette):
                return super().polish(obj)

            super().polish(obj)
            if isinstance(obj, QComboBox):
                return self._install_menu_popup(obj)

        @staticmethod
        def _install_menu_popup(combo):
            def _show_popup(combo=combo):
                from qtpy.QtCore import Qt, QPoint

                if (old := getattr(combo, "_popup_menu", None)) is not None:
                    old.deleteLater()

                # Parent the popup to the combo's top-level window rather
                # than to the combo itself.  Inside a QDockWidget the chain
                # combo -> intermediate plain QWidget -> ... -> main window
                # makes Qt materialize a non-top-level QWidgetWindow when
                # resolving the popup's transient parent, which triggers
                # "QWidgetWindow ... must be a top level window" warnings.
                menu = QMenu(combo.window() or combo)
                menu.setStyleSheet(
                    "QMenu { padding: 0px 0px; }" "QMenu::item { padding: 4px 7px; }"
                )
                menu.setWindowFlags(
                    menu.windowFlags()
                    | Qt.WindowType.FramelessWindowHint
                    | Qt.WindowType.NoDropShadowWindowHint
                )
                menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
                menu.setMinimumWidth(combo.width())

                current = combo.currentIndex()
                for i in range(combo.count()):
                    action = menu.addAction(combo.itemText(i))
                    if i == current:
                        f = action.font()
                        f.setWeight(500)
                        action.setFont(f)
                    action.triggered.connect(
                        lambda _, idx=i: combo.setCurrentIndex(idx)
                    )

                menu.popup(combo.mapToGlobal(QPoint(0, 0)))
                combo._popup_menu = menu

            combo.showPopup = _show_popup

    return MosaicStyle()


def switch_theme(palette: dict):
    """Switch the active theme.

    Parameters
    ----------
    palette : dict
        One of ``Colors.LIGHT``, ``Colors.DARK``, or a custom palette dict.
    """
    from qtpy.QtWidgets import QApplication

    Colors.apply_palette(palette)
    if (app := QApplication.instance()) is None:
        return None

    app.setPalette(build_qt_palette())
    app.setStyleSheet(build_global_stylesheet())
    for widget in app.allWidgets():
        if hasattr(widget, "_on_theme_changed"):
            widget._on_theme_changed()
    if sys.platform == "darwin":
        for window in app.topLevelWidgets():
            ns_win = _get_nswindow(window)
            if ns_win is not None:
                _update_macos_titlebar_color(ns_win)
