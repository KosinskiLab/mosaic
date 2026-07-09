"""
Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

from mosaic.stylesheets import Colors
from mosaic.icons import _resolve_colors, icon, icon_pixmap, icon_button


def test_resolve_colors_defaults_to_muted_enabled_and_disabled():
    color, color_disabled = _resolve_colors(
        role="muted", color=None, color_disabled=None
    )
    assert color == Colors.ICON
    assert color_disabled == Colors.ICON


def test_resolve_colors_active_enabled_muted_disabled():
    color, color_disabled = _resolve_colors(
        role="active", color=None, color_disabled=None
    )
    assert color == Colors.ICON_ACTIVE
    assert color_disabled == Colors.ICON


def test_resolve_colors_primary_enabled_muted_disabled():
    color, color_disabled = _resolve_colors(
        role="primary", color=None, color_disabled=None
    )
    assert color == Colors.PRIMARY
    assert color_disabled == Colors.ICON


def test_resolve_colors_explicit_color_bypasses_role():
    color, color_disabled = _resolve_colors(
        role="muted", color="#ff00ff", color_disabled=None
    )
    assert color == "#ff00ff"
    assert color_disabled == Colors.ICON


def test_resolve_colors_explicit_color_disabled_wins():
    color, color_disabled = _resolve_colors(
        role="active", color=None, color_disabled="#123456"
    )
    assert color == Colors.ICON_ACTIVE
    assert color_disabled == "#123456"


def test_resolve_colors_unknown_role_raises():
    import pytest

    with pytest.raises(ValueError, match="unknown icon role"):
        _resolve_colors(role="bogus", color=None, color_disabled=None)


def test_icon_factory_returns_qicon(qtbot):
    from qtpy.QtGui import QIcon

    result = icon("ph.upload", role="active")
    assert isinstance(result, QIcon)
    assert not result.isNull()


def test_icon_pixmap_returns_nonempty_pixmap(qtbot):
    from qtpy.QtGui import QPixmap

    pix = icon_pixmap("ph.info", 18, role="primary")
    assert isinstance(pix, QPixmap)
    assert pix.width() == 18
    assert pix.height() == 18


def test_icon_button_constructs_enabled_and_disabled(qtbot):
    from qtpy.QtWidgets import QPushButton
    from qtpy.QtGui import QIcon

    btn = icon_button("ph.upload", tooltip="Upload")
    qtbot.addWidget(btn)
    assert isinstance(btn, QPushButton)
    assert btn.toolTip() == "Upload"
    assert not btn.icon().isNull()
    btn.setEnabled(False)

    # Qt generates a disabled pixmap using our color_disabled
    disabled_pix = btn.icon().pixmap(22, 22, mode=QIcon.Mode.Disabled)
    assert not disabled_pix.isNull()


def test_icon_falls_back_for_unknown_glyph(qtbot):
    """An unknown glyph name produces a warning and a non-null placeholder."""
    import warnings

    from qtpy.QtGui import QIcon

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = icon("ph.this-glyph-definitely-does-not-exist-xyz")

    assert isinstance(result, QIcon)
    assert not result.isNull()
    assert any("unavailable" in str(w.message) for w in caught)


def test_icon_pixmap_falls_back_for_unknown_glyph(qtbot):
    """``icon_pixmap`` inherits the fallback path from ``icon``."""
    import warnings

    from qtpy.QtGui import QPixmap

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        pix = icon_pixmap("ph.another-missing-glyph", 16)

    assert isinstance(pix, QPixmap)
    assert pix.width() == 16
    assert pix.height() == 16
    assert any("unavailable" in str(w.message) for w in caught)
