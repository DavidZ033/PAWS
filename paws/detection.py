"""Dog detection.

Uses YOLOX, a small object detector trained on the COCO dataset, run
through OpenCV's built-in DNN module from an ONNX file. That keeps the
dependency list short: no TensorFlow or PyTorch is needed on the Pi.

A background thread checks the newest camera frame about once a second.
When a dog appears after being out of view, an event is logged with a
snapshot that has the bounding box drawn on it.

The model file is not stored in the repository. Fetch it once with:

    python -m paws download-model

Two sizes are available through ``detection.model`` in config.yaml:
    yolox_tiny  20 MB, more accurate (default)
    yolox_nano  4 MB, roughly three times faster, misses more
"""

from __future__ import annotations

import logging
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from paws.camera import Camera
from paws.events import EventLog

log = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]

MODEL_URL = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/{name}.onnx"
MODELS = ("yolox_tiny", "yolox_nano")
STRIDES = (8, 16, 32)

# The 80 COCO classes, in the order the model outputs them.
COCO_LABELS = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog",
    "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
    "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant",
    "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard",
    "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair dryer", "toothbrush",
]


def download_model(model_dir: str, name: str = "yolox_tiny", force: bool = False) -> None:
    """Download the detector file into ``model_dir``."""
    if name not in MODELS:
        raise ValueError(f"Unknown model '{name}'. Choose from: {', '.join(MODELS)}")
    target = Path(model_dir)
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{name}.onnx"
    if path.is_file() and not force:
        print(f"  {path.name}: already present")
        return
    print(f"  {path.name}: downloading...")
    tmp = path.with_suffix(".part")
    urllib.request.urlretrieve(MODEL_URL.format(name=name), tmp)
    tmp.replace(path)
    print(f"  {path.name}: {path.stat().st_size / 1e6:.1f} MB")


class DogDetector:
    def __init__(self, cfg: Dict[str, Any], camera: Camera, events: EventLog) -> None:
        self.cfg = cfg
        self.camera = camera
        self.events = events
        self.enabled = bool(cfg.get("enabled", True))
        self.model_dir = Path(cfg.get("model_dir", "models"))
        self.model_name = cfg.get("model", "yolox_tiny")
        wanted = cfg.get("labels", ["dog"])
        unknown = [name for name in wanted if name not in COCO_LABELS]
        if unknown:
            raise ValueError(f"Unknown detection labels: {unknown}")
        self.class_ids = [COCO_LABELS.index(name) for name in wanted]
        self.confidence = float(cfg.get("confidence", 0.4))
        self.interval = float(cfg.get("interval", 1.0))
        self.input_size = int(cfg.get("input_size", 416))
        self.cooldown = float(cfg.get("event_cooldown", 60))
        self.lost_after = float(cfg.get("lost_after", 5))

        self.available = False
        self.reason: Optional[str] = "not started"
        self.dog_present = False
        self.best: Optional[Dict[str, Any]] = None
        self.last_seen: Optional[float] = None
        self._last_event = 0.0
        self._net: Any = None
        self._grid: Any = None
        self._stride: Any = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def load(self) -> bool:
        """Load the network. Returns False (with ``reason`` set) on failure."""
        if cv2 is None:
            self.reason = "OpenCV (cv2) is not installed"
            return False
        path = self.model_dir / f"{self.model_name}.onnx"
        if not path.is_file():
            self.reason = f"model file {path} is missing. Run: python -m paws download-model"
            return False
        try:
            self._net = cv2.dnn.readNetFromONNX(str(path))
        except Exception as exc:  # noqa: BLE001
            self.reason = f"could not load model: {exc}"
            return False
        # YOLOX predicts on three grids (coarse, medium, fine). Precompute
        # each cell's position and size so raw outputs can be turned into
        # pixel boxes.
        grids, strides = [], []
        for stride in STRIDES:
            n = self.input_size // stride
            xs, ys = np.meshgrid(np.arange(n), np.arange(n))
            grids.append(np.stack((xs, ys), axis=2).reshape(-1, 2))
            strides.append(np.full((n * n, 1), stride))
        self._grid = np.concatenate(grids).astype(np.float32)
        self._stride = np.concatenate(strides).astype(np.float32)
        self.available = True
        self.reason = None
        return True

    def detect(self, frame: Any) -> List[Dict[str, Any]]:
        """Run the detector on one BGR frame.

        Returns the matching objects, most confident first. Each one is
        ``{"label", "confidence", "box": [x, y, width, height]}`` in pixels.
        """
        if self._net is None:
            return []
        size = self.input_size
        height, width = frame.shape[:2]

        # Shrink to fit a square, keeping the shape, and pad the rest grey.
        ratio = min(size / height, size / width)
        resized = cv2.resize(frame, (max(1, int(width * ratio)), max(1, int(height * ratio))))
        canvas = np.full((size, size, 3), 114, dtype=np.uint8)
        canvas[: resized.shape[0], : resized.shape[1]] = resized

        self._net.setInput(cv2.dnn.blobFromImage(canvas, 1.0, (size, size), swapRB=False))
        out = self._net.forward()[0]  # one row per grid cell: x, y, w, h, objectness, 80 class scores

        centres = (out[:, :2] + self._grid) * self._stride
        sizes = np.exp(out[:, 2:4]) * self._stride
        found: List[Dict[str, Any]] = []
        for class_id in self.class_ids:
            scores = out[:, 4] * out[:, 5 + class_id]
            keep = scores >= self.confidence
            if not keep.any():
                continue
            boxes = np.concatenate((centres[keep] - sizes[keep] / 2, sizes[keep]), axis=1) / ratio
            kept_scores = scores[keep]
            # Many neighbouring cells report the same object. Keep the best.
            chosen = cv2.dnn.NMSBoxes(boxes.tolist(), kept_scores.tolist(), self.confidence, 0.45)
            for i in np.array(chosen).flatten():
                x, y, w, h = boxes[i]
                x, y = max(0, int(x)), max(0, int(y))
                found.append({
                    "label": COCO_LABELS[class_id],
                    "confidence": round(float(kept_scores[i]), 3),
                    "box": [x, y, min(int(w), width - x), min(int(h), height - y)],
                })
        found.sort(key=lambda d: d["confidence"], reverse=True)
        return found

    def process(self, frame: Any, now: Optional[float] = None) -> List[Dict[str, Any]]:
        """Detect on a frame and update presence state and the event log."""
        now = time.time() if now is None else now
        found = self.detect(frame)
        if found:
            was_present = self.dog_present
            self.dog_present = True
            self.best = found[0]
            self.last_seen = now
            if not was_present and now - self._last_event >= self.cooldown:
                self._last_event = now
                self.events.add(
                    "dog_detected",
                    f"{found[0]['label'].capitalize()} spotted ({found[0]['confidence']:.0%} confident)",
                    {"detections": found},
                    snapshot=self._annotated(frame, found),
                )
        elif self.dog_present and self.last_seen is not None and now - self.last_seen > self.lost_after:
            self.dog_present = False
            self.best = None
        return found

    def _annotated(self, frame: Any, found: List[Dict[str, Any]]) -> Optional[bytes]:
        image = frame.copy()
        for det in found:
            x, y, w, h = det["box"]
            cv2.rectangle(image, (x, y), (x + w, y + h), (0, 220, 0), 2)
            cv2.putText(
                image, f"{det['label']} {det['confidence']:.0%}", (x, max(18, y - 6)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 0), 2,
            )
        return self.camera.encode(image)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="detector")
        self._thread.start()

    def _loop(self) -> None:
        if not self.load():
            log.warning("Dog detection unavailable: %s", self.reason)
            return
        log.info("Dog detection ready")
        while self._running:
            started = time.monotonic()
            if self.enabled:
                frame = self.camera.get_frame()
                if frame is not None:
                    try:
                        self.process(frame)
                    except Exception:  # noqa: BLE001
                        log.exception("Detection failed on a frame")
            time.sleep(max(0.05, self.interval - (time.monotonic() - started)))

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "available": self.available,
            "reason": self.reason,
            "dog_present": self.dog_present,
            "confidence": self.best["confidence"] if self.best else None,
            "box": self.best["box"] if self.best else None,
            "last_seen": self.last_seen,
        }

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None
