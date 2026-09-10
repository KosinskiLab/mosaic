import textwrap

from mosaic.dialogs.import_data import ImportDataDialog
from mosaic.formats._utils import read_star_header
from mosaic.widgets.settings import get_widget_value


RELION4_PIXEL_STAR = textwrap.dedent(
    """\
    data_optics

    loop_
    _rlnOpticsGroup #1
    _rlnImagePixelSize #2
               1     6.43832


    data_particles

    loop_
    _rlnCoordinateX #1
    _rlnCoordinateY #2
    _rlnCoordinateZ #3
    _rlnAngleRot #4
    _rlnAngleTilt #5
    _rlnAnglePsi #6
        100.0    200.0    300.0    0.0    0.0    0.0
        110.0    210.0    310.0    0.0    0.0    0.0
"""
)

RELION5_CENTERED_STAR = textwrap.dedent(
    """\
    # version 50001

    data_optics

    loop_
    _rlnOpticsGroup #1
    _rlnImagePixelSize #2
               1     6.43832


    # version 50001

    data_particles

    loop_
    _rlnCenteredCoordinateXAngst #1
    _rlnCenteredCoordinateYAngst #2
    _rlnCenteredCoordinateZAngst #3
    _rlnAngleRot #4
    _rlnAngleTilt #5
    _rlnAnglePsi #6
        100.0    200.0    300.0    0.0    0.0    0.0
"""
)

LEGACY_STAR_NO_OPTICS = textwrap.dedent(
    """\
    data_

    loop_
    _rlnCoordinateX #1
    _rlnCoordinateY #2
    _rlnCoordinateZ #3
        100.0    200.0    300.0
"""
)


def test_default_state_mirrors_sampling_into_scale(qapp, tmp_path):
    """With override off, get_all_parameters reports scale == sampling_rate."""
    dialog = ImportDataDialog()
    fake = str(tmp_path / "points.txt")
    open(fake, "w").close()
    dialog.set_files([fake])

    assert not dialog.override_checkbox.isChecked()
    assert dialog.scale_x.isHidden()
    assert dialog.scale_label.isHidden()

    dialog.sampling_x.setText("2.5")  # propagates to y, z via existing handler

    params = dialog.get_all_parameters()[fake]
    assert params["sampling_rate"] == (2.5, 2.5, 2.5)
    assert params["scale"] == params["sampling_rate"]


def test_toggle_on_off_cycle_resets_scale(qapp, tmp_path):
    """Enabling override pre-fills scale from sampling; disabling forgets edits."""
    dialog = ImportDataDialog()
    fake = str(tmp_path / "points.txt")
    open(fake, "w").close()
    dialog.set_files([fake])

    dialog.sampling_x.setText("2.5")  # propagates to y/z

    dialog.override_checkbox.setChecked(True)
    assert not dialog.scale_x.isHidden()
    assert get_widget_value(dialog.scale_x) == 2.5
    assert get_widget_value(dialog.scale_y) == 2.5
    assert get_widget_value(dialog.scale_z) == 2.5

    dialog.scale_x.setText("0.85")  # user edits scale (propagates to y, z)
    assert get_widget_value(dialog.scale_x) == 0.85

    dialog.override_checkbox.setChecked(False)
    assert dialog.scale_x.isHidden()

    dialog.override_checkbox.setChecked(True)
    # Pre-fill from current sampling, NOT the previously-edited 0.85
    assert get_widget_value(dialog.scale_x) == 2.5


def test_per_file_override_persistence(qapp, tmp_path):
    """Override state and scale values are preserved when navigating between files."""
    dialog = ImportDataDialog()
    f1 = str(tmp_path / "f1.txt")
    f2 = str(tmp_path / "f2.txt")
    open(f1, "w").close()
    open(f2, "w").close()
    dialog.set_files([f1, f2])

    # File 1: sampling 2.0, override on, scale 0.85
    dialog.sampling_x.setText("2.0")
    dialog.override_checkbox.setChecked(True)
    dialog.scale_x.setText("0.85")

    # Navigate to file 2 — fresh defaults
    dialog.next_file()
    assert not dialog.override_checkbox.isChecked()
    assert dialog.scale_x.isHidden()

    # Navigate back — file 1 state restored
    dialog.previous_file()
    assert dialog.override_checkbox.isChecked()
    assert not dialog.scale_x.isHidden()
    assert get_widget_value(dialog.scale_x) == 0.85
    assert get_widget_value(dialog.sampling_x) == 2.0


def test_read_star_header_relion4_pixel(tmp_path):
    f = tmp_path / "r4.star"
    f.write_text(RELION4_PIXEL_STAR)

    info = read_star_header(str(f))

    assert info["pixel_size"] == 6.43832
    assert info["centered"] is False


def test_read_star_header_relion5_centered(tmp_path):
    f = tmp_path / "r5.star"
    f.write_text(RELION5_CENTERED_STAR)

    info = read_star_header(str(f))

    assert info["pixel_size"] == 6.43832
    assert info["centered"] is True


def test_read_star_header_no_optics(tmp_path):
    f = tmp_path / "legacy.star"
    f.write_text(LEGACY_STAR_NO_OPTICS)

    info = read_star_header(str(f))

    assert info["pixel_size"] is None
    assert info["centered"] is False


def test_read_star_header_malformed(tmp_path):
    f = tmp_path / "broken.star"
    f.write_text("this is not a star file at all")

    info = read_star_header(str(f))

    # Either an empty dict (parse failure swallowed) or both keys present
    # with safe defaults; the only contract we promise callers is "no exception".
    assert isinstance(info, dict)


def test_set_files_relion4_prefills_sampling(qapp, tmp_path):
    f = tmp_path / "r4.star"
    f.write_text(RELION4_PIXEL_STAR)

    dialog = ImportDataDialog()
    dialog.set_files([str(f)])

    assert get_widget_value(dialog.sampling_x) == 6.43832
    assert get_widget_value(dialog.sampling_y) == 6.43832
    assert get_widget_value(dialog.sampling_z) == 6.43832
    assert not dialog.override_checkbox.isChecked()

    # Auto-tied scale: when override is off, get_all_parameters returns scale == sampling
    params = dialog.get_all_parameters()[str(f)]
    assert params["sampling_rate"] == (6.43832, 6.43832, 6.43832)
    assert params["scale"] == params["sampling_rate"]


def test_set_files_relion5_centered_enables_override(qapp, tmp_path):
    f = tmp_path / "r5.star"
    f.write_text(RELION5_CENTERED_STAR)

    dialog = ImportDataDialog()
    dialog.set_files([str(f)])

    assert get_widget_value(dialog.sampling_x) == 6.43832
    assert dialog.override_checkbox.isChecked()
    assert get_widget_value(dialog.scale_x) == 1.0
    assert get_widget_value(dialog.scale_y) == 1.0
    assert get_widget_value(dialog.scale_z) == 1.0

    # Offset stays at default zero; user re-centers manually.
    params = dialog.get_all_parameters()[str(f)]
    assert params["offset"] == (0.0, 0.0, 0.0)
    assert params["scale"] == (1.0, 1.0, 1.0)
    assert params["sampling_rate"] == (6.43832, 6.43832, 6.43832)


def test_set_files_legacy_star_keeps_defaults(qapp, tmp_path):
    f = tmp_path / "legacy.star"
    f.write_text(LEGACY_STAR_NO_OPTICS)

    dialog = ImportDataDialog()
    dialog.set_files([str(f)])

    assert get_widget_value(dialog.sampling_x) == 1.0
    assert not dialog.override_checkbox.isChecked()

    params = dialog.get_all_parameters()[str(f)]
    assert params["sampling_rate"] == (1.0, 1.0, 1.0)
    assert params["scale"] == params["sampling_rate"]
    assert params["offset"] == (0.0, 0.0, 0.0)
