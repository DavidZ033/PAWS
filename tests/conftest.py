import copy

import pytest

from paws.config import DEFAULTS, deep_merge
from paws.robot import Robot


def make_config(**overrides):
    base = deep_merge(
        copy.deepcopy(DEFAULTS),
        {
            "robot": {"simulate": True},
            "camera": {"backend": "synthetic", "fps": 30},
            "detection": {"enabled": False, "model_dir": "/nonexistent"},
            "feeder": {"open_time": 0.01, "pause_between_portions": 0.01},
        },
    )
    return deep_merge(base, overrides)


@pytest.fixture
def config():
    return make_config()


@pytest.fixture
def robot(config):
    """A simulated robot that is NOT running its own loop. Tests call step()."""
    r = Robot(config, persist=False)
    yield r
    r.shutdown()
