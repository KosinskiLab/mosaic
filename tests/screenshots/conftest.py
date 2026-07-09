import sys
import pytest
import numpy as np
from pathlib import Path
from PIL import Image

from qtpy.QtGui import QFont, QFontInfo, QFontDatabase
from qtpy.QtWidgets import QApplication

from mosaic.stylesheets import (
    Colors,
    Typography,
    build_global_stylesheet,
    build_qt_palette,
)


SCREENSHOT_DIR = Path(__file__).resolve().parents[2] / "docs" / "_static" / "tutorial"


@pytest.fixture(scope="session")
def qapp():
    if QApplication.instance():
        app = QApplication.instance()
    else:
        app = QApplication(sys.argv)

    app.setApplicationName("Mosaic")
    app.setStyle("Fusion")

    Colors.apply_palette(Colors.LIGHT)

    if sys.platform == "darwin":
        font = QFont("Helvetica Neue")
        if "Helvetica Neue" not in QFontDatabase.families():
            font = app.font()
        font.setPointSize(13)
        app.setFont(font)

    Typography.set_base(QFontInfo(app.font()).pixelSize())
    app.setPalette(build_qt_palette())
    app.setStyleSheet(build_global_stylesheet())

    yield app


@pytest.fixture(scope="module")
def mosaic_app(qapp):
    from mosaic.gui import App

    window = App()
    window.show()
    window.resize(1440, 900)
    qapp.processEvents()

    # Force the tab pill indicator to its final position — the animation
    # is deferred via QTimer.singleShot(0, ...) and needs event processing,
    # then we skip the animation and snap it into place.
    qapp.processEvents()
    window.tab_bar._anim.stop()
    btn = window.tab_bar._buttons[0]
    h = 28
    from qtpy.QtCore import QRect

    window.tab_bar._indicator.setGeometry(
        QRect(btn.x(), (window.tab_bar.height() - h) // 2, btn.width(), h)
    )

    yield window
    window.close()


@pytest.fixture(scope="session")
def output_dir():
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    return SCREENSHOT_DIR


def _grab_widget_to_image(widget):
    from qtpy.QtGui import QImage

    pixmap = widget.grab()
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    width = image.width()
    height = image.height()
    ptr = image.constBits()
    ptr.setsize(height * width * 4)
    arr = np.frombuffer(ptr, np.uint8).reshape(height, width, 4).copy()
    return Image.fromarray(arr[:, :, :3])


def _round_corners(img, radius=10):
    """Apply anti-aliased rounded-corner alpha mask matching macOS window chrome."""
    from PIL import ImageDraw

    w, h = img.size
    # Render mask at 4x for anti-aliased edges, then downsample
    scale = 4
    sw, sh, sr = w * scale, h * scale, radius * scale
    mask_hi = Image.new("L", (sw, sh), 255)
    draw = ImageDraw.Draw(mask_hi)
    draw.rectangle([0, 0, sr, sr], fill=0)
    draw.rectangle([sw - sr, 0, sw, sr], fill=0)
    draw.rectangle([0, sh - sr, sr, sh], fill=0)
    draw.rectangle([sw - sr, sh - sr, sw, sh], fill=0)
    draw.ellipse([0, 0, sr * 2, sr * 2], fill=255)
    draw.ellipse([sw - sr * 2, 0, sw, sr * 2], fill=255)
    draw.ellipse([0, sh - sr * 2, sr * 2, sh], fill=255)
    draw.ellipse([sw - sr * 2, sh - sr * 2, sw, sh], fill=255)
    mask = mask_hi.resize((w, h), Image.LANCZOS)

    result = img.convert("RGBA")
    result.putalpha(mask)
    return result


def save_widget_screenshot(widget, path: Path):
    img = _grab_widget_to_image(widget)
    if widget.isWindow():
        img = _round_corners(img)
    img.save(str(path))


def save_app_screenshot(app_window, path: Path):
    img = app_window.screenshot_manager.capture_window()
    img = _round_corners(img)
    img.save(str(path))


def make_sphere_points(n_theta=30, n_phi=30, radius=50.0, noise=0.5, seed=42):
    rng = np.random.RandomState(seed)
    theta = np.linspace(0.1, np.pi - 0.1, n_theta)
    phi = np.linspace(0, 2 * np.pi, n_phi, endpoint=False)
    t, p = np.meshgrid(theta, phi)
    t, p = t.ravel(), p.ravel()
    r = radius + rng.normal(0, noise, len(t))
    points = np.column_stack(
        [
            r * np.sin(t) * np.cos(p),
            r * np.sin(t) * np.sin(p),
            r * np.cos(t),
        ]
    ).astype(np.float32)
    return points


def make_two_blobs(n_per_blob=200, separation=120.0, seed=42):
    rng = np.random.RandomState(seed)
    blob_a = rng.randn(n_per_blob, 3).astype(np.float32) * 15
    blob_b = rng.randn(n_per_blob, 3).astype(np.float32) * 15
    blob_b[:, 0] += separation
    return np.vstack([blob_a, blob_b])
