"""Autonomous driving to points on the floor.

The navigator is a small state machine. Each control-loop tick the robot
hands it the current pose and it hands back a drive command. It never
touches the motors itself, which makes it easy to test.

Control is a plain proportional controller: the further from the target,
the harder it drives, up to a speed cap. Because the X-drive can move in any
direction, x, y and heading are corrected at the same time.

Coordinates are in the odometry frame: metres from where the robot started,
x forward, y left, heading counter-clockwise in radians.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from paws.odometry import Pose, wrap_angle


@dataclass
class Waypoint:
    x: float
    y: float
    theta: Optional[float] = None  # None = keep whatever heading we have

    def as_dict(self) -> Dict[str, Any]:
        return {"x": self.x, "y": self.y, "theta": self.theta}


class Navigator:
    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.kp_linear = float(cfg.get("kp_linear", 1.5))
        self.kp_angular = float(cfg.get("kp_angular", 1.5))
        self.max_power = float(cfg.get("max_power", 0.5))
        self.max_turn_power = float(cfg.get("max_turn_power", 0.4))
        self.min_power = float(cfg.get("min_power", 0.12))
        self.position_tolerance = float(cfg.get("position_tolerance", 0.05))
        self.heading_tolerance = float(cfg.get("heading_tolerance", 0.1))
        self.timeout = float(cfg.get("timeout", 30))

        self.state = "idle"  # idle, running, reached, timeout, cancelled
        self.waypoints: List[Waypoint] = []
        self.index = 0
        self.loops_left = 0
        self.forever = False
        self.distance_to_target: Optional[float] = None
        self._elapsed = 0.0

    @property
    def active(self) -> bool:
        return self.state == "running"

    @property
    def target(self) -> Optional[Waypoint]:
        return self.waypoints[self.index] if self.active and self.index < len(self.waypoints) else None

    def goto(self, x: float, y: float, theta: Optional[float] = None) -> None:
        self.patrol([Waypoint(float(x), float(y), theta)], loops=1)

    def patrol(self, waypoints: List[Waypoint], loops: int = 1) -> None:
        """Visit each waypoint in order, ``loops`` times. 0 loops = forever."""
        if not waypoints:
            raise ValueError("at least one waypoint is required")
        self.waypoints = list(waypoints)
        self.index = 0
        self.forever = loops <= 0
        self.loops_left = max(1, loops)
        self._elapsed = 0.0
        self.distance_to_target = None
        self.state = "running"

    def cancel(self) -> None:
        if self.active:
            self.state = "cancelled"

    def update(self, pose: Pose, dt: float) -> Optional[Tuple[float, float, float]]:
        """Return ``(vx, vy, omega)`` for this tick, or None when not driving."""
        if not self.active:
            return None
        wp = self.waypoints[self.index]
        self._elapsed += dt
        if self._elapsed > self.timeout:
            self.state = "timeout"
            return None

        ex, ey = wp.x - pose.x, wp.y - pose.y
        distance = math.hypot(ex, ey)
        etheta = wrap_angle(wp.theta - pose.theta) if wp.theta is not None else 0.0
        self.distance_to_target = distance

        if distance <= self.position_tolerance and abs(etheta) <= self.heading_tolerance:
            return self._advance()

        # The error is in field coordinates. Rotate it into the robot's own
        # frame so "forward" means the direction the robot is facing now.
        cos_t, sin_t = math.cos(pose.theta), math.sin(pose.theta)
        fwd = cos_t * ex + sin_t * ey
        left = -sin_t * ex + cos_t * ey

        speed = min(self.max_power, self.kp_linear * distance)
        if distance > self.position_tolerance:
            speed = max(speed, self.min_power)
            vx, vy = speed * fwd / distance, speed * left / distance
        else:
            vx = vy = 0.0

        omega = max(-self.max_turn_power, min(self.max_turn_power, self.kp_angular * etheta))
        if abs(etheta) > self.heading_tolerance and abs(omega) < self.min_power:
            omega = math.copysign(self.min_power, etheta)
        elif abs(etheta) <= self.heading_tolerance / 2:
            omega = 0.0
        return vx, vy, omega

    def _advance(self) -> Optional[Tuple[float, float, float]]:
        self.index += 1
        self._elapsed = 0.0
        if self.index >= len(self.waypoints):
            if not self.forever:
                self.loops_left -= 1
            if self.forever or self.loops_left > 0:
                self.index = 0
            else:
                self.state = "reached"
                return None
        return 0.0, 0.0, 0.0

    def status(self) -> Dict[str, Any]:
        target = self.target
        return {
            "state": self.state,
            "active": self.active,
            "target": target.as_dict() if target else None,
            "waypoint_index": self.index if self.active else None,
            "waypoint_count": len(self.waypoints) if self.active else 0,
            "distance_to_target": round(self.distance_to_target, 3) if self.active and self.distance_to_target is not None else None,
        }
