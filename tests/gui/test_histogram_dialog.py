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
