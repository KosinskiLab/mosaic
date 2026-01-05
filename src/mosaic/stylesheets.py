from importlib_resources import files

__all__ = [
    "Colors",
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
    "QToolButton_style",
    "QMenu_style",
    "QDockWidget_style",
    "QTable_style",
]


class Colors:
    """Centralized color definitions for the Mosaic application."""

    PRIMARY = "#4f46e5"  # Indigo - main accent color

    # =========================================================================
    # Text Colors
    # =========================================================================
    TEXT_PRIMARY = "#334155"  # Slate 700 - main text, headings
    TEXT_SECONDARY = "#64748b"  # Slate 500 - secondary text, labels, icons
    TEXT_MUTED = "#6b7280"  # Gray 500 - muted/placeholder text

    # =========================================================================
    # Border Colors
    # =========================================================================
    BORDER_HOVER = "#94a3b8"  # Slate 400 - border on hover
    BORDER_DARK = "#cbd5e1"  # Slate 300 - default borders

    # =========================================================================
    # Background Colors
    # =========================================================================
    BG_SECONDARY = "#f8fafc"  # Slate 50 - subtle background
    BG_TERTIARY = "#f1f5f9"  # Slate 100 - disabled/muted background
    BG_HOVER = "rgba(0, 0, 0, 0.06)"  # Hover state
    BG_PRESSED = "rgba(0, 0, 0, 0.10)"  # Pressed state

    # =========================================================================
    # Status Colors
    # =========================================================================
    SUCCESS = "#10b981"  # Emerald 500
    SUCCESS_BG = "#d1fae5"  # Emerald 100
    SUCCESS_TEXT = "#065f46"  # Emerald 800

    WARNING = "#f59e0b"  # Amber 500
    WARNING_DARK = "#d97706"  # Amber 600
    WARNING_BG = "#fef3c7"  # Amber 100
    WARNING_TEXT = "#92400e"  # Amber 800

    ERROR = "#ef4444"  # Red 500
    ERROR_BG = "#fee2e2"  # Red 100
    ERROR_TEXT = "#991b1b"  # Red 800

    NEUTRAL = "#6b7280"  # Gray 500
    NEUTRAL_BG = "#e5e7eb"  # Gray 200
    NEUTRAL_TEXT = "#374151"  # Gray 700

    # =========================================================================
    # Icon Colors
    # =========================================================================
    ICON = "#64748b"  # Slate 500 - primary icon color
    ICON_MUTED = "#9ca3af"  # Gray 400 - muted icons, chevrons

    # =========================================================================
    # Entity Colors (for "By Entity" coloring mode)
    # =========================================================================
    ENTITY = [
        (0.90, 0.25, 0.20),  # Vermillion red
        (0.18, 0.62, 0.78),  # Cerulean
        (0.98, 0.75, 0.18),  # Saffron
        (0.32, 0.70, 0.40),  # Malachite
        (0.72, 0.32, 0.78),  # Amethyst
        (0.95, 0.50, 0.20),  # Tangerine
        (0.22, 0.42, 0.72),  # Cobalt
        (0.85, 0.35, 0.55),  # Cerise
        (0.45, 0.75, 0.30),  # Chartreuse
        (0.55, 0.25, 0.60),  # Plum
        (0.20, 0.68, 0.58),  # Viridian
        (0.92, 0.58, 0.45),  # Coral
        (0.35, 0.35, 0.75),  # Ultramarine
        (0.75, 0.72, 0.25),  # Olive gold
        (0.78, 0.25, 0.38),  # Carmine
        (0.25, 0.78, 0.72),  # Turquoise
        (0.65, 0.45, 0.20),  # Bronze
        (0.52, 0.58, 0.85),  # Periwinkle
        (0.88, 0.40, 0.70),  # Fuchsia
        (0.38, 0.58, 0.28),  # Moss
        (0.70, 0.55, 0.65),  # Mauve
        (0.28, 0.55, 0.45),  # Teal
        (0.82, 0.65, 0.55),  # Peach
        (0.48, 0.38, 0.55),  # Grape
    ]

    # =========================================================================
    # Category Colors (for pipelines, animations, etc.)
    # =========================================================================
    CATEGORY = {
        # Pipeline operation categories
        "input": "#7c3aed",  # Violet 600
        "preprocessing": "#2563eb",  # Blue 600
        "parametrization": "#059669",  # Emerald 600
        "export": "#ea580c",  # Orange 600
        # Animation types
        "trajectory": "#3b82f6",  # Blue 500
        "camera": "#10b981",  # Emerald 500
        "zoom": "#14b8a6",  # Teal 500
        "volume": "#f59e0b",  # Amber 500
        "visibility": "#8b5cf6",  # Violet 500
        "waypoint": "#ec4899",  # Pink 500
        # Pipeline presets
        "clear": "#ef4444",  # Red 500
        "import": "#3b82f6",  # Blue 500
        "cleanup": "#8b5cf6",  # Violet 500
        "meshing": "#10b981",  # Emerald 500
        "particle_picking": "#f59e0b",  # Amber 500
    }


def _get_resource_path(resource_name):
    """Get the absolute path to a resource in the package.

    Args:
        resource_name (str): Relative path to the resource within the
            package data directory

    Returns:
        str: The absolute path to the resource
    """
    return str(files("mosaic.data").joinpath(f"data/{resource_name}"))


HelpLabel_style = f"""
    QLabel {{
        color: {Colors.TEXT_MUTED};
        font-size: 12px;
        border-top: 0px;
    }}
"""

QGroupBox_style = f"""
    QGroupBox {{
        font-weight: 500;
        border: 1px solid {Colors.BORDER_DARK};
        border-radius: 6px;
        margin-top: 6px;
        padding-top: 14px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 7px;
        padding: 0px 5px 0px 5px;
    }}
"""

QPushButton_style = f"""
    QPushButton {{
        border: 1px solid {Colors.BORDER_DARK};
        border-radius: 4px;
        padding: 6px 12px;
    }}
    QPushButton:hover {{
        background: {Colors.BG_HOVER};
        border: 1px solid rgba(0, 0, 0, 0.08);
    }}
    QPushButton:pressed {{
        background: {Colors.BG_PRESSED};
        border: 1px solid rgba(0, 0, 0, 0.12);
    }}
    QPushButton:focus {{
        outline: none;
    }}
"""

QLineEdit_style = f"""
    QLineEdit {{
        border: 1px solid {Colors.BORDER_DARK};
        border-radius: 4px;
        padding: 4px 8px;
        selection-background-color: rgba(99, 102, 241, 0.6);
        background: transparent;
    }}
    QLineEdit:focus {{
        outline: none;
        border: 1px solid {Colors.PRIMARY};
    }}
    QLineEdit:hover:!focus {{
        border: 1px solid {Colors.BORDER_HOVER};
    }}
    QLineEdit:disabled {{
        background-color: {Colors.BG_TERTIARY};
        color: {Colors.BORDER_HOVER};
    }}
"""

QSpinBox_style = f"""
    QSpinBox {{
        border: 1px solid {Colors.BORDER_DARK};
        border-radius: 4px;
        padding: 4px 8px;
        background-color: transparent;
        selection-background-color: rgba(99, 102, 241, 0.6);
    }}
    QSpinBox:focus {{
        outline: none;
        border: 1px solid {Colors.PRIMARY};
    }}
    QSpinBox:hover:!focus {{
        border: 1px solid {Colors.BORDER_HOVER};
    }}
    QSpinBox:disabled {{
        background-color: {Colors.BG_TERTIARY};
        color: {Colors.BORDER_HOVER};
    }}
    QSpinBox::up-button, QSpinBox::down-button {{
        border: 1px solid {Colors.BORDER_DARK};
        width: 16px;
        background-color: {Colors.BG_SECONDARY};
    }}
    QSpinBox::up-button {{
        border-top-right-radius: 3px;
        border-bottom: none;
    }}
    QSpinBox::down-button {{
        border-bottom-right-radius: 3px;
    }}
    QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
        background-color: {Colors.BG_TERTIARY};
        border-color: {Colors.BORDER_HOVER};
    }}
    QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {{
        background-color: #e2e8f0;
    }}
"""


QDoubleSpinBox_style = f"""
    QDoubleSpinBox {{
        border: 1px solid {Colors.BORDER_DARK};
        border-radius: 4px;
        padding: 4px 8px;
        background-color: transparent;
        selection-background-color: rgba(99, 102, 241, 0.6);
    }}
    QDoubleSpinBox:focus {{
        outline: none;
        border: 1px solid {Colors.PRIMARY};
    }}
    QDoubleSpinBox:hover:!focus {{
        border: 1px solid {Colors.BORDER_HOVER};
    }}
    QDoubleSpinBox:disabled {{
        background-color: {Colors.BG_TERTIARY};
        color: {Colors.BORDER_HOVER};
    }}
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        border: 1px solid {Colors.BORDER_DARK};
        width: 16px;
        background-color: {Colors.BG_SECONDARY};
    }}
    QDoubleSpinBox::up-button {{
        border-top-right-radius: 3px;
        border-bottom: none;
    }}
    QDoubleSpinBox::down-button {{
        border-bottom-right-radius: 3px;
    }}
    QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
        background-color: {Colors.BG_TERTIARY};
        border-color: {Colors.BORDER_HOVER};
    }}
    QDoubleSpinBox::up-button:pressed, QDoubleSpinBox::down-button:pressed {{
        background-color: #e2e8f0;
    }}
"""


QComboBox_style = f"""
    QComboBox {{
        border: 1px solid {Colors.BORDER_DARK};
        border-radius: 4px;
        min-height: 27px;
        padding: 0px 8px;
        background: transparent;
        selection-background-color: rgba(99, 102, 241, 0.6);
    }}
    QComboBox:focus {{
        outline: none;
        border: 1px solid {Colors.PRIMARY};
    }}
    QComboBox:hover:!focus {{
        border: 1px solid {Colors.BORDER_HOVER};
    }}
    QComboBox:disabled {{
        background-color: {Colors.BG_TERTIARY};
        color: {Colors.BORDER_HOVER};
    }}
    QComboBox::drop-down:disabled {{
        border: none;
    }}
    QComboBox QAbstractItemView {{
        border: 1px solid {Colors.BORDER_DARK};
        border-radius: 4px;
        selection-background-color: rgba(99, 102, 241, 0.3);
    }}
"""

QCheckBox_style = f"""
    QCheckBox {{
        spacing: 5px;
        background-color: transparent;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border: 1px solid {Colors.BORDER_DARK};
    }}
    QCheckBox::indicator:checked {{
        image: url('{_get_resource_path("checkbox-checkmark.svg")}')
    }}
"""

QScrollArea_style = f"""
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

QTabBar_style = f"""
    QTabBar::tab {{
        background: transparent;
        border: 1px solid {Colors.BORDER_DARK};
        border-bottom: none;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        padding: 6px 12px;
        margin-right: 2px;
    }}
    QTabBar::tab:selected {{
        color: {Colors.PRIMARY};
        border-color: {Colors.PRIMARY};
    }}
    QTabBar::tab:hover:!selected {{
        color: {Colors.TEXT_MUTED};
    }}
    /* Style for the tab widget itself */
    QTabWidget::pane {{
        border: 1px solid {Colors.BORDER_DARK};
        background-color: transparent;
        border-top-right-radius: 6px;
        border-bottom-right-radius: 6px;
        border-bottom-left-radius: 6px;
    }}

    /* Style for the tab contents */
    QWidget#scrollContentWidget {{
        background-color: transparent;
    }}

    /* Make scroll areas transparent */
    QScrollArea {{
        background-color: transparent;
        border: none;
    }}

"""


QTable_style = f"""
    QTableWidget {{
        border: 1px solid {Colors.BORDER_DARK};
        border-radius: 4px;
        background-color: transparent;
        outline: none;
        gridline-color: {Colors.BORDER_DARK};
    }}
    QTableWidget::item {{
        border: none;
    }}
    QTableWidget::item:hover {{
        background-color: {Colors.BG_HOVER};
    }}
    QTableWidget::item:selected {{
        background-color: rgba(99, 102, 241, 0.3);
    }}
    QTableWidget QHeaderView::section {{
        background-color: {Colors.BG_SECONDARY};
        border: none;
        border-right: 1px solid {Colors.BORDER_DARK};
        border-bottom: 1px solid {Colors.BORDER_DARK};
        padding: 2px 4px;
    }}
    QTableWidget QHeaderView::section:hover {{
        background-color: {Colors.BG_TERTIARY};
    }}
    QTableWidget QTableCornerButton::section {{
        background-color: {Colors.BG_SECONDARY};
        border: none;
        border-right: 1px solid {Colors.BORDER_DARK};
        border-bottom: 1px solid {Colors.BORDER_DARK};
    }}
"""

QListWidget_style = f"""
    QListWidget {{
        border: none;
        background-color: transparent;
        outline: none;
        padding: 4px 0px;
    }}
    QListWidget::item {{
        border-radius: 6px;
        margin: 2px 8px;
        font-size: 13px;
    }}
    QListWidget::item:hover {{
        background-color: {Colors.BG_PRESSED};
    }}
    QListWidget::item:selected {{
        background-color: rgba(99, 102, 241, 0.3);
        font-weight: 500;
    }}
"""

# Left background used to be #4f46e5
QSlider_style = f"""
    QSlider {{
        height: 24px;
    }}
    QSlider:disabled {{
        opacity: 0.5;
    }}
    QSlider::groove:horizontal {{
        height: 4px;
        background: #e2e8f0;
        border-radius: 2px;
    }}
    QSlider::groove:horizontal:disabled {{
        background: {Colors.BG_TERTIARY};
    }}
    QSlider::handle:horizontal {{
        background: #ffffff;
        border: 1px solid {Colors.BORDER_DARK};
        width: 16px;
        height: 16px;
        margin: -6px 0;
        border-radius: 8px;
    }}
    QSlider::handle:horizontal:hover {{
        border-color: {Colors.PRIMARY};
    }}
    QSlider::handle:horizontal:focus {{
        border: 1px solid {Colors.PRIMARY};
        background: #f9fafb;
    }}
    QSlider::handle:horizontal:disabled {{
        background: {Colors.BG_SECONDARY};
        border: 1px solid #e2e8f0;
    }}
    QSlider::sub-page:horizontal {{
        background: {Colors.BORDER_HOVER};
        border-radius: 2px;
    }}
    QSlider::sub-page:horizontal:disabled {{
        background: {Colors.BORDER_DARK};
    }}
"""

QMessageBox_style = f"""
    QMessageBox QLabel {{
        font-size: 13px;
    }}
    QMessageBox QPushButton {{
        border: 1px solid {Colors.BORDER_DARK};
        border-radius: 4px;
        padding: 6px 16px;
        min-width: 80px;
    }}
    QMessageBox QPushButton:hover {{
        border: 1px solid {Colors.ICON_MUTED};
        background: {Colors.BG_HOVER};
    }}
    QMessageBox QPushButton:pressed {{
        border: 1px solid {Colors.ICON_MUTED};
        background: rgba(0, 0, 0, 0.24);
    }}
    QMessageBox QPushButton:focus {{
        outline: none;
    }}
    QMessageBox QCheckBox {{
        color: {Colors.TEXT_PRIMARY};
        font-size: 12px;
    }}
    QMessageBox QTextEdit {{
        border: 1px solid {Colors.BORDER_DARK};
        border-radius: 4px;
        padding: 8px;
    }}
"""

QProgressBar_style = f"""
    QProgressBar {{
        border: none;
        background-color: {Colors.NEUTRAL_BG};
        border-radius: 4px;
        height: 8px;
    }}
    QProgressBar::chunk {{
        background-color: {Colors.PRIMARY};
        border-radius: 4px;
    }}
"""


QToolButton_style = f"""
    QToolButton {{
        min-width: 52px;
        padding: 4px 6px;
        border-radius: 6px;
        font-size: 11px;
        background: transparent;
        border: 1px solid transparent;
    }}
    QToolButton:hover {{
        background: {Colors.BG_HOVER};
        border: 1px solid rgba(0, 0, 0, 0.08);
    }}
    QToolButton:pressed {{
        background: {Colors.BG_PRESSED};
        border: 1px solid rgba(0, 0, 0, 0.12);
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

QMenu_style = f"""
    QMenu {{
        border: 1px solid {Colors.BORDER_DARK};
        border-radius: 8px;
        padding: 4px;
    }}
    QMenu::item {{
        padding: 4px 12px;
        border-radius: 4px;
        border: 1px solid transparent;
    }}
    QMenu::item:selected {{
        background: {Colors.BG_HOVER};
        border: 1px solid rgba(0, 0, 0, 0.08);
    }}
    QMenu::item:pressed {{
        background: {Colors.BG_PRESSED};
        border: 1px solid rgba(0, 0, 0, 0.12);
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
    }}
    QMenu::indicator:checked {{
        image: url('{_get_resource_path("checkbox-checkmark.svg")}');
    }}
"""

QDockWidget_style = f"""
    QDockWidget {{
        titlebar-close-icon: url('{_get_resource_path("dock-close.svg")}');
        titlebar-normal-icon: url('{_get_resource_path("dock-float.svg")}');
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
        border: 1px solid rgba(0, 0, 0, 0.08);
    }}
    QDockWidget::close-button:pressed, QDockWidget::float-button:pressed {{
        background: {Colors.BG_PRESSED};
        border: 1px solid rgba(0, 0, 0, 0.12);
    }}
"""
