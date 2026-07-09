"""Functional tests for the global UndoStack primitive."""

from mosaic.undo import STACK, UndoEntry, UndoStack


def _entry(state, before, after, label="op"):
    return UndoEntry(
        label=label,
        undo=lambda: state.__setitem__("v", before),
        redo=lambda: state.__setitem__("v", after),
    )


def test_empty_stack_is_inert():
    stack = UndoStack()
    assert stack.undo() is None
    assert stack.redo() is None


def test_push_then_undo_runs_undo_fn():
    state = {"v": 0}
    stack = UndoStack()
    state["v"] = 5
    stack.push(_entry(state, before=0, after=5))
    assert stack.undo() is not None
    assert state["v"] == 0
    assert stack.undo() is None


def test_redo_replays_after_undo():
    state = {"v": 0}
    stack = UndoStack()
    state["v"] = 5
    stack.push(_entry(state, before=0, after=5))
    stack.undo()
    assert stack.redo() is not None
    assert state["v"] == 5
    assert stack.redo() is None


def test_pushing_clears_redo():
    state = {"v": 0}
    stack = UndoStack()
    stack.push(_entry(state, 0, 1, label="a"))
    stack.undo()
    stack.push(_entry(state, 1, 2, label="b"))
    assert stack.redo() is None


def test_capacity_evicts_oldest():
    state = {"v": 0}
    stack = UndoStack(capacity=2)
    stack.push(_entry(state, 0, 1, label="a"))
    stack.push(_entry(state, 1, 2, label="b"))
    stack.push(_entry(state, 2, 3, label="c"))
    assert stack.undo().label == "c"
    assert stack.undo().label == "b"
    assert stack.undo() is None


def test_clear_drops_both_directions():
    state = {"v": 0}
    stack = UndoStack()
    stack.push(_entry(state, 0, 1))
    stack.undo()
    stack.clear()
    assert stack.undo() is None and stack.redo() is None


def test_singleton_is_a_real_undo_stack():
    assert isinstance(STACK, UndoStack)
