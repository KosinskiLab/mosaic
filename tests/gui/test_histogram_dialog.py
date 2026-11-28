from qtpy.QtWidgets import QPushButton

from mosaic.dialogs.histogram import HistogramWidget


def _spy(widget):
    calls = []
    widget.cutoff_changed.connect(lambda lo, hi: calls.append((lo, hi)))
    return calls


def test_redraw_does_not_emit_cutoff(qapp):
    widget = HistogramWidget()
    calls = _spy(widget)
    widget.update_histogram([10, 20, 30, 40])
    widget.update_histogram([10, 20, 30])
    assert calls == []


def test_user_cutoff_emits(qapp):
    widget = HistogramWidget()
    widget.update_histogram([10, 20, 30, 40])
    calls = _spy(widget)
    widget.min_value_input.setText("15")
    widget._handle_input_change(is_lower=True)
    assert len(calls) == 1 and calls[0][0] == 15


def test_redraw_keeps_chosen_bounds(qapp):
    widget = HistogramWidget()
    widget.update_histogram([10, 20, 30, 40])
    widget.min_value_input.setText("15")
    widget._handle_input_change(is_lower=True)

    widget.update_histogram([10, 20, 30, 40, 50])

    assert widget.bounds == (15, 50)


def test_bound_at_edge_follows_new_data(qapp):
    widget = HistogramWidget()
    widget.update_histogram([10, 20, 30, 40])
    widget.update_histogram([5, 20, 30, 80])
    assert widget.bounds == (5, 80)


def test_scale_switch_keeps_bounds_silently(qapp):
    widget = HistogramWidget()
    widget.update_histogram([10, 200, 3000, 40000])
    widget.max_value_input.setText("3000")
    widget._handle_input_change(is_lower=False)
    calls = _spy(widget)

    linear = next(b for b in widget.findChildren(QPushButton) if b.text() == "Linear")
    linear.click()

    assert widget.bounds == (10, 3000)
    assert calls == []


def test_log_slider_emits_cluster_sizes(qapp):
    widget = HistogramWidget()
    widget.update_histogram([10, 200, 3000, 40000])
    calls = _spy(widget)

    widget._on_slider(2.0, 3.0)

    assert calls == [(100, 1000)]
