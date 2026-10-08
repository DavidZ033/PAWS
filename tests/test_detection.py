"""Detector tests. These need the model file, so they are skipped until
``python -m paws download-model`` has been run."""

from pathlib import Path

import numpy as np
import pytest

from paws.camera import Camera
from paws.config import DEFAULTS
from paws.detection import DogDetector
from paws.events import EventLog

MODEL = Path("models/yolox_tiny.onnx")
pytestmark = pytest.mark.skipif(not MODEL.is_file(), reason="detection model not downloaded")


@pytest.fixture
def detector(tmp_path):
    cfg = {**DEFAULTS["detection"], "model_dir": "models"}
    det = DogDetector(cfg, Camera(DEFAULTS["camera"], simulated=True), EventLog(str(tmp_path)))
    assert det.load(), det.reason
    return det


def test_empty_room_has_no_dog(detector):
    frame = np.full((480, 640, 3), 90, dtype=np.uint8)
    assert detector.process(frame) == []
    assert detector.dog_present is False
    assert detector.events.list() == []


def test_presence_times_out(detector):
    detector.dog_present, detector.last_seen = True, 100.0
    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    detector.process(blank, now=102.0)
    assert detector.dog_present is True  # brief dropouts are tolerated
    detector.process(blank, now=110.0)
    assert detector.dog_present is False
