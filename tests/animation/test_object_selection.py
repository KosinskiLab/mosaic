from types import SimpleNamespace

import numpy as np
import pytest

from mosaic.animation.animations import ActorSelectionDialog
from mosaic.geometry import Geometry
from mosaic.tree_state import TreeStateData


class _Data:
    def __init__(self, clusters, models, groups=None):
        self._objects = {"data": clusters, "models": models}
        self.data = self._interactor(clusters, groups or {})
        self.models = self._interactor(models, {})

    @staticmethod
    def _interactor(objects, groups):
        state = TreeStateData()
        grouped = {uuid for members in groups.values() for uuid in members}
        state.root_items = [g.uuid for g in objects if g.uuid not in grouped]
        for name, members in groups.items():
            state.groups[name] = members
            state.group_names[name] = name
            state.root_items.append(name)
        return SimpleNamespace(data_list=SimpleNamespace(to_state=lambda: state))

    def format_datalist(self, data_type):
        return [(g._meta["name"], g) for g in self._objects[data_type]]


def _geometry(name, visible=True):
    g = Geometry(points=np.random.default_rng(0).random((5, 3)), meta={"name": name})
    g.set_visibility(visible)
    return g


@pytest.fixture
def scene(qapp):
    clusters = [_geometry("membrane"), _geometry("ribosome"), _geometry("noise", False)]
    models = [_geometry("mesh")]
    return clusters, models


def test_preselects_current_selection(scene):
    clusters, models = scene
    dialog = ActorSelectionDialog(
        _Data(clusters, models), current_selection=[id(clusters[1])]
    )
    assert dialog.get_selected_objects() == [id(clusters[1])]
    assert dialog._count.text() == "1 of 4 selected"


@pytest.mark.parametrize(
    "data_types, expected",
    [
        (("data", "models"), 4),
        (("data",), 3),
        (("models",), 1),
        ((), 0),
    ],
)
def test_quick_select(scene, data_types, expected):
    dialog = ActorSelectionDialog(_Data(*scene))
    dialog._select(data_types)
    assert len(dialog.get_selected_objects()) == expected


def test_quick_select_respects_filter(scene):
    clusters, models = scene
    dialog = ActorSelectionDialog(_Data(clusters, models))
    dialog._filter("mem")
    dialog._select(("data", "models"))
    assert dialog.get_selected_objects() == [id(clusters[0])]


def test_grouped_objects_are_listed_and_filtered(scene):
    clusters, models = scene
    groups = {"organelles": [clusters[0].uuid, clusters[1].uuid]}
    dialog = ActorSelectionDialog(_Data(clusters, models, groups))

    dialog._select(("data",))
    assert set(dialog.get_selected_objects()) == {id(g) for g in clusters}

    dialog._filter("mesh")
    tree = dialog._trees["data"].tree_widget
    assert all(tree.topLevelItem(i).isHidden() for i in range(tree.topLevelItemCount()))
