"""Camera capture.

A background thread grabs frames continuously and keeps only the newest one.
Everything else (the live stream, snapshots, dog detection) reads that
latest frame, so a slow consumer never blocks the camera.

Backends:
    picamera2  Raspberry Pi camera module (the normal case on the robot)
    opencv     any USB webcam
    synthetic  a generated test pattern, used in simulation
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]


class Camera:
    def __init__(self, cfg: Dict[str, Any], simulated: bool = False) -> None:
        self.cfg = cfg
        self.simulated = simulated
        self.width = int(cfg.get("width", 640))
        self.height = int(cfg.get("height", 480))
        self.fps = max(1, int(cfg.get("fps", 15)))
        self.quality = int(cfg.get("jpeg_quality", 70))
        self.rotate = int(cfg.get("rotate", 0))
        self.backend = "none"
        self.error: Optional[str] = None
        self._source: Any = None
        self._frame: Any = None
        self._frame_id = 0
        self._jpeg: Optional[bytes] = None
        self._jpeg_id = -1
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    @property
    def available(self) -> bool:
        return self._running and self.backend != "none"

    def start(self) -> None:
        if self._running:
            return
        if not self.cfg.get("enabled", True):
            self.error = "disabled in config"
            return
        if cv2 is None:
            self.error = "OpenCV (cv2) is not installed"
            log.warning("Camera unavailable: %s", self.error)
            return
        self._open()
        if self.backend == "none":
            log.warning("Camera unavailable: %s", self.error)
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="camera")
        self._thread.start()
        log.info("Camera started (%s, %dx%d @ %d fps)", self.backend, self.width, self.height, self.fps)

    def _open(self) -> None:
        wanted = self.cfg.get("backend", "auto")
        if wanted == "auto":
            order = ["synthetic"] if self.simulated else ["picamera2", "opencv"]
        else:
            order = [wanted]
        errors = []
        for name in order:
            try:
                if name == "picamera2":
                    from picamera2 import Picamera2

                    cam = Picamera2()
                    # Picamera2 calls this format RGB888, but the bytes come
                    # out in BGR order, which is exactly what OpenCV expects.
                    cam.configure(
                        cam.create_video_configuration(main={"size": (self.width, self.height), "format": "RGB888"})
                    )
                    cam.start()
                    self._source = cam
                elif name == "opencv":
                    cap = cv2.VideoCapture(int(self.cfg.get("device", 0)))
                    if not cap.isOpened():
                        cap.release()
                        raise RuntimeError("could not open video device")
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                    self._source = cap
                elif name == "synthetic":
                    self._source = None
                else:
                    raise ValueError(f"unknown camera backend '{name}'")
                self.backend = name
                self.error = None
                return
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{name}: {exc}")
        self.error = "; ".join(errors)

    def _grab(self) -> Any:
        if self.backend == "picamera2":
            return self._source.capture_array()
        if self.backend == "opencv":
            ok, frame = self._source.read()
            return frame if ok else None
        return self._synthetic()

    def _synthetic(self) -> Any:
        """Test pattern: dark background, a moving block and a clock."""
        t = time.time()
        frame = np.full((self.height, self.width, 3), 40, dtype=np.uint8)
        size = self.height // 6
        x = int((t * 80) % max(1, self.width - size))
        y = self.height // 2 - size // 2
        cv2.rectangle(frame, (x, y), (x + size, y + size), (80, 180, 250), -1)
        cv2.putText(frame, "PAWS simulated camera", (16, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.putText(frame, time.strftime("%H:%M:%S"), (16, self.height - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        return frame

    def _loop(self) -> None:
        period = 1.0 / self.fps
        failures = 0
        while self._running:
            started = time.monotonic()
            try:
                frame = self._grab()
            except Exception as exc:  # noqa: BLE001
                frame = None
                self.error = str(exc)
            if frame is None:
                failures += 1
                if failures == 30:
                    log.warning("Camera is not returning frames (%s)", self.error)
                time.sleep(0.1)
                continue
            failures = 0
            if self.rotate == 90:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            elif self.rotate == 180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            elif self.rotate == 270:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
            with self._lock:
                self._frame = frame
                self._frame_id += 1
            time.sleep(max(0.0, period - (time.monotonic() - started)))

    def get_frame(self) -> Any:
        """Newest frame as a BGR numpy array, or None."""
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def get_jpeg(self) -> Tuple[int, Optional[bytes]]:
        """Newest frame as ``(frame_id, jpeg_bytes)``.

        Encoding happens at most once per frame however many clients ask.
        """
        with self._lock:
            if self._frame is None:
                return self._frame_id, None
            if self._jpeg_id != self._frame_id:
                self._jpeg = self.encode(self._frame)
                self._jpeg_id = self._frame_id
            return self._frame_id, self._jpeg

    def encode(self, frame: Any) -> Optional[bytes]:
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
        return buf.tobytes() if ok else None

    def status(self) -> Dict[str, Any]:
        return {
            "available": self.available,
            "backend": self.backend,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "error": self.error,
        }

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        try:
            if self.backend == "picamera2" and self._source is not None:
                self._source.stop()
                self._source.close()
            elif self.backend == "opencv" and self._source is not None:
                self._source.release()
        except Exception:  # noqa: BLE001
            pass
        self._source = None
