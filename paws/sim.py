"""A very small physics model for running without the robot.

It assumes the robot instantly moves at whatever speed the motors are
commanded to, then rolls the two simulated tracking wheels by the amount
real ones would have turned. That is enough to exercise the odometry and
navigation code end to end on a laptop.
"""

from __future__ import annotations

import math
from typing import Tuple

from paws.hardware.encoder import Encoder
from paws.odometry import Odometry, Pose, wrap_angle


class SimPhysics:
    def __init__(self, odometry: Odometry, enc1: Encoder, enc2: Encoder, max_speed: float, max_turn_rate: float) -> None:
        self.odometry = odometry
        self.enc1 = enc1
        self.enc2 = enc2
        self.max_speed = max_speed
        self.max_turn_rate = max_turn_rate
        self.true_pose = Pose()

    def step(self, applied: Tuple[float, float, float], dt: float) -> None:
        vx, vy, omega = applied
        dx = vx * self.max_speed * dt
        dy = vy * self.max_speed * dt
        dtheta = omega * self.max_turn_rate * dt

        mid = self.true_pose.theta + dtheta / 2.0
        self.true_pose.x += dx * math.cos(mid) - dy * math.sin(mid)
        self.true_pose.y += dx * math.sin(mid) + dy * math.cos(mid)
        self.true_pose.theta = wrap_angle(self.true_pose.theta + dtheta)

        odo = self.odometry
        if odo.layout == "parallel":
            self.enc1.simulate_move(dx - dtheta * odo.track_width / 2.0)
            self.enc2.simulate_move(dx + dtheta * odo.track_width / 2.0)
        else:
            self.enc1.simulate_move(dx - dtheta * odo.enc1_offset)
            self.enc2.simulate_move(dy + dtheta * odo.enc2_offset)
