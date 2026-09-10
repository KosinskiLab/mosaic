from unittest.mock import MagicMock
import numpy as np

from mosaic.sculpt.controller import MeshHit, pick_mesh


def test_pick_mesh_miss_returns_none():
    picker = MagicMock()
    picker.Pick.return_value = 0
    renderer = MagicMock()
    hit = pick_mesh(picker, renderer, screen_x=100, screen_y=100, actor=MagicMock())
    assert hit is None


def test_pick_mesh_hit_returns_meshhit():
    picker = MagicMock()
    picker.Pick.return_value = 1
    picker.GetPickPosition.return_value = (1.0, 2.0, 3.0)
    picker.GetPickNormal.return_value = (0.0, 0.0, 1.0)
    actor = "an_actor"
    picker.GetActor.return_value = actor
    renderer = MagicMock()
    hit = pick_mesh(picker, renderer, screen_x=100, screen_y=100, actor=actor)
    assert isinstance(hit, MeshHit)
    assert np.array_equal(hit.world_position, [1.0, 2.0, 3.0])
    assert np.array_equal(hit.normal, [0.0, 0.0, 1.0])


def test_pick_mesh_wrong_actor_returns_none():
    picker = MagicMock()
    picker.Pick.return_value = 1
    picker.GetActor.return_value = "some_other_actor"
    renderer = MagicMock()
    hit = pick_mesh(picker, renderer, screen_x=100, screen_y=100, actor="target_actor")
    assert hit is None
