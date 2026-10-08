"""Servo food dispenser.

Positional mode: the servo swings a gate open, waits, then closes it. One
open/close cycle is one portion.

Continuous mode: the servo (set to continuous rotation) turns an auger or
paddle wheel for a fixed time per portion.

Dispensing runs on a background thread so the caller gets an answer right
away. A second request while one is in progress is refused.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional

from paws.hardware.servo import ServoOutput


class Feeder:
    def __init__(self, servo: ServoOutput, cfg: Dict[str, Any], sleep: Callable[[float], None] = time.sleep) -> None:
        self.servo = servo
        self.mode = cfg.get("mode", "positional")
        if self.mode not in ("positional", "continuous"):
            raise ValueError(f"Unknown feeder mode: {self.mode}")
        self.closed_position = float(cfg.get("closed_position", -1.0))
        self.open_position = float(cfg.get("open_position", 0.0))
        self.open_time = float(cfg.get("open_time", 1.0))
        self.pause = float(cfg.get("pause_between_portions", 0.5))
        self.continuous_speed = float(cfg.get("continuous_speed", 0.5))
        self.max_portions = int(cfg.get("max_portions", 5))
        self.detach_when_idle = bool(cfg.get("detach_when_idle", True))
        self.last_fed: Optional[float] = None
        self.total_portions = 0
        self._sleep = sleep
        self._busy = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> "Feeder":
        servo = ServoOutput(cfg["pin"], cfg.get("min_pulse_ms", 0.5), cfg.get("max_pulse_ms", 2.5))
        return cls(servo, cfg)

    @property
    def busy(self) -> bool:
        return self._busy.locked()

    def clamp_portions(self, portions: int) -> int:
        return max(1, min(self.max_portions, int(portions)))

    def dispense(self, portions: int = 1, wait: bool = False) -> bool:
        """Start dispensing. Returns False if the feeder is already busy."""
        portions = self.clamp_portions(portions)
        if not self._busy.acquire(blocking=False):
            return False
        self._thread = threading.Thread(target=self._run, args=(portions,), daemon=True, name="feeder")
        self._thread.start()
        if wait:
            self._thread.join()
        return True

    def _run(self, portions: int) -> None:
        try:
            for i in range(portions):
                if self.mode == "positional":
                    self.servo.set(self.open_position)
                    self._sleep(self.open_time)
                    self.servo.set(self.closed_position)
                else:
                    self.servo.set(self.continuous_speed)
                    self._sleep(self.open_time)
                    self.servo.set(0.0)
                self.total_portions += 1
                if i < portions - 1:
                    self._sleep(self.pause)
            # Give the gate time to finish closing before cutting the signal.
            self._sleep(0.4)
            if self.detach_when_idle:
                self.servo.detach()
            self.last_fed = time.time()
        finally:
            self._busy.release()

    def status(self) -> Dict[str, Any]:
        return {"busy": self.busy, "last_fed": self.last_fed, "total_portions": self.total_portions, "mode": self.mode}

    def close(self) -> None:
        if self._thread is not None:
            self._thread.join(timeout=5)
        self.servo.close()
