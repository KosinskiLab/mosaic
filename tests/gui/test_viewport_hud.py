from types import SimpleNamespace

import pytest
from qtpy.QtCore import QPoint, QRect, QSize
from qtpy.QtWidgets import QLabel, QVBoxLayout, QWidget

from mosaic.widgets.sculpt_palette_hud import SculptPaletteHUD
from mosaic.widgets.viewport_hud import ViewportHUD


class _CornerHUD(ViewportHUD):
    def __init__(self, parent):
        super().__init__(parent)
        QVBoxLayout(self).addWidget(QLabel("hud"))

    def anchor(self, viewport: QRect, size: QSize) -> QPoint:
        return viewport.bottomRight() - QPoint(size.width(), size.height())


@pytest.fixture
def window(qapp):
    main = QWidget()
    viewport = QWidget(main)
    viewport.setGeometry(20, 30, 400, 300)
    main.resize(500, 400)
    main.show()
    yield main, viewport
    main.close()


def _viewport_rect(viewport):
    return QRect(viewport.mapToGlobal(QPoint(0, 0)), viewport.size())


def test_hud_follows_viewport_resize(window, qapp):
    main, viewport = window
    hud = _CornerHUD(main)
    hud.attach_to_viewport(viewport)
    hud.show()

    viewport.resize(300, 200)
    qapp.processEvents()

    corner = _viewport_rect(viewport).bottomRight()
    assert hud.geometry().bottomRight() == corner - QPoint(1, 1)


def test_hud_hides_and_returns_with_window(window, qapp):
    main, viewport = window
    hud = _CornerHUD(main)
    hud.attach_to_viewport(viewport)
    hud.show()

    main.hide()
    assert not hud.isVisible()
    main.show()
    assert hud.isVisible()


def test_sculpt_palette_sits_bottom_left(window, qapp):
    main, viewport = window
    palette = SculptPaletteHUD(main)
    palette.attach(SimpleNamespace(viewport_container=viewport))
    palette.show()
    qapp.processEvents()

    rect = _viewport_rect(viewport)
    margin = palette._MARGIN
    assert palette.geometry().left() == rect.left() + margin
    assert palette.geometry().bottom() == rect.bottom() - margin
