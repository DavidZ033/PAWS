"""Position tracking from the two encoder wheels.

The pose is (x, y, theta) in the "field" frame, which is simply wherever the
robot was sitting and facing when the program started (or when the pose was
last reset). x points forward from that starting pose, y points left, theta
is counter-clockwise.

Two layouts are supported:

perpendicular (default)
    enc1 rolls forward/back and enc2 rolls sideways. This measures x and y
    directly but two wheels alone cannot measure rotation, so heading comes
    from ``heading_source``:
        "commanded"  integrate the turn command (drifts, but needs no parts)
        "none"       assume the robot never turns
    Adding a gyro (for example a BNO055 on I2C) and feeding its angle into
    ``update(heading=...)`` is the best upgrade for accuracy.

parallel
    enc1 is on the left and enc2 on the right, both rolling forward. This
    measures forward travel and heading, but not sideways sliding.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional

from paws.hardware.encoder import Encoder


def wrap_angle(angle: float) -> float:
    """Wrap to (-pi, pi]."""
    return math.atan2(math.sin(angle), math.cos(angle))


@dataclass
class Pose:
    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0

    def as_dict(self) -> Dict[str, float]:
        return {
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "theta": round(self.theta, 4),
            "theta_deg": round(math.degrees(self.theta), 1),
        }


class Odometry:
    def __init__(self, enc1: Encoder, enc2: Encoder, cfg: Dict[str, Any], max_turn_rate: float = 3.0) -> None:
        self.enc1 = enc1
        self.enc2 = enc2
        self.layout = cfg.get("layout", "perpendicular")
        if self.layout not in ("perpendicular", "parallel"):
            raise ValueError(f"Unknown odometry layout: {self.layout}")
        self.heading_source = cfg.get("heading_source", "commanded")
        self.enc1_offset = float(cfg.get("enc1_offset", 0.0))
        self.enc2_offset = float(cfg.get("enc2_offset", 0.0))
        self.track_width = float(cfg.get("track_width", 0.2))
        self.max_turn_rate = float(max_turn_rate)
        self._pose = Pose()
        self._lock = threading.Lock()
        self._last1 = enc1.distance
        self._last2 = enc2.distance

    @property
    def pose(self) -> Pose:
        with self._lock:
            return Pose(self._pose.x, self._pose.y, self._pose.theta)

    def reset(self, x: float = 0.0, y: float = 0.0, theta: float = 0.0) -> None:
        with self._lock:
            self._pose = Pose(float(x), float(y), wrap_angle(float(theta)))
            self._last1 = self.enc1.distance
            self._last2 = self.enc2.distance

    def update(self, dt: float, omega_cmd: float = 0.0, heading: Optional[float] = None) -> Pose:
        """Read both encoders and advance the pose.

        ``omega_cmd`` is the turn command currently applied (-1..1).
        ``heading`` is an absolute heading in radians from a gyro, if you
        have one. When given it overrides every other heading estimate.
        """
        with self._lock:
            d1_now, d2_now = self.enc1.distance, self.enc2.distance
            d1, d2 = d1_now - self._last1, d2_now - self._last2
            self._last1, self._last2 = d1_now, d2_now
            theta = self._pose.theta

            if self.layout == "parallel":
                dtheta = (d2 - d1) / self.track_width
                if heading is not None:
                    dtheta = wrap_angle(heading - theta)
                dx, dy = (d1 + d2) / 2.0, 0.0
            else:
                if heading is not None:
                    dtheta = wrap_angle(heading - theta)
                elif self.heading_source == "commanded":
                    dtheta = omega_cmd * self.max_turn_rate * dt
                else:
                    dtheta = 0.0
                # A tracking wheel mounted off-centre also rolls when the
                # robot spins on the spot. Remove that part.
                dx = d1 + dtheta * self.enc1_offset
                dy = d2 - dtheta * self.enc2_offset

            # Rotate the robot-frame step into the field frame, using the
            # heading halfway through the step for better accuracy on curves.
            mid = theta + dtheta / 2.0
            self._pose.x += dx * math.cos(mid) - dy * math.sin(mid)
            self._pose.y += dx * math.sin(mid) + dy * math.cos(mid)
            self._pose.theta = wrap_angle(theta + dtheta)
            return Pose(self._pose.x, self._pose.y, self._pose.theta)
