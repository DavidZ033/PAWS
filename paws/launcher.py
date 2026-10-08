"""Ball launcher: two flywheels that spin in opposite directions.

A ball dropped between the wheels gets pinched and thrown. ``launch`` spins
the wheels for a few seconds and then shuts them off by itself, so a dropped
WiFi connection can never leave the flywheels running.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

from paws.hardware.motor import Motor


class Launcher:
    def __init__(self, motors: List[Motor], cfg: Dict[str, Any]) -> None:
        self.motors = motors
        self.default_power = float(cfg.get("default_power", 0.8))
        self.default_duration = float(cfg.get("default_duration", 3.0))
        self.max_run_time = float(cfg.get("max_run_time", 10.0))
        self.power = 0.0
        self.last_launch: Optional[float] = None
        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> "Launcher":
        motors = [
            Motor.from_config(f"launcher_{name}", mcfg, pwm_frequency=cfg.get("pwm_frequency", 1000))
            for name, mcfg in cfg["motors"].items()
        ]
        return cls(motors, cfg)

    @property
    def running(self) -> bool:
        return self.power > 0.0

    def launch(self, power: Optional[float] = None, duration: Optional[float] = None) -> Dict[str, float]:
        """Spin the flywheels at ``power`` (0..1) for ``duration`` seconds."""
        power = self.default_power if power is None else float(power)
        duration = self.default_duration if duration is None else float(duration)
        power = max(0.0, min(1.0, power))
        duration = max(0.1, min(self.max_run_time, duration))
        with self._lock:
            self._cancel_timer()
            for motor in self.motors:
                motor.set(power)
            self.power = power
            self.last_launch = time.time()
            self._timer = threading.Timer(duration, self.stop)
            self._timer.daemon = True
            self._timer.start()
        return {"power": power, "duration": duration}

    def stop(self) -> None:
        with self._lock:
            self._cancel_timer()
            for motor in self.motors:
                motor.stop()
            self.power = 0.0

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def status(self) -> Dict[str, Any]:
        return {"running": self.running, "power": round(self.power, 3), "last_launch": self.last_launch}

    def close(self) -> None:
        self.stop()
        for motor in self.motors:
            motor.close()
