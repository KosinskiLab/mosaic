from types import SimpleNamespace

import numpy as np

from mosaic import parallel
from mosaic.geometry import Geometry
from mosaic.tabs import model
from mosaic.tabs.model import ModelTab
from mosaic.tabs.segmentation import SegmentationTab


def _tab(names):
    geometries = [
        Geometry(points=np.zeros((4, 3)), meta={"name": name}) for name in names
    ]
    selection = SimpleNamespace(get_selected_geometries=lambda: geometries)
    return SimpleNamespace(
        cdata=SimpleNamespace(data=selection, models=selection),
        _default_callback=lambda *args, **kwargs: None,
        _get_selected_meshes=lambda: geometries,
    )


def test_fit_tasks_name_their_geometry(monkeypatch, qapp):
    submitted = []
    monkeypatch.setattr(model, "submit_task_batch", submitted.extend)
    ModelTab._fit_parallel(_tab(["Cluster 10", "Cluster 15"]), "ball_pivoting")
    names = [task["name"] for task in submitted]
    assert len(set(names)) == 2
    assert all(any(c in n for n in names) for c in ("Cluster 10", "Cluster 15"))


def test_segmentation_tasks_name_their_geometry(monkeypatch, qapp):
    submitted = []
    monkeypatch.setattr(
        parallel, "submit_task", lambda name, *args, **kwargs: submitted.append(name)
    )
    SegmentationTab._run_op(_tab(["Cluster 10", "Cluster 15"]), "cluster")
    assert len(set(submitted)) == 2
    assert all(any(c in n for n in submitted) for c in ("Cluster 10", "Cluster 15"))


def test_failure_dialog_keeps_the_geometry_name(monkeypatch, qapp):
    import mosaic.widgets

    shown = []

    class Box:
        def __init__(self, icon, title, text, buttons):
            shown.append(text)

        def __getattr__(self, name):
            return lambda *args, **kwargs: []

    monkeypatch.setattr(mosaic.widgets, "MosaicMessageBox", Box)
    parallel._pending_messages.append(
        ("Parametrization PR8-TS23_open_surface", "boom", False)
    )
    parallel._flush_messages()
    assert "PR8-TS23_open_surface" in shown[0]
