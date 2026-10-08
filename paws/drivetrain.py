"""X-drive (holonomic) drivetrain.

Four omni wheels sit at the corners of the robot, each turned 45 degrees.
Because every wheel can also slide sideways on its rollers, the robot can
drive in any direction and spin at the same time.

Conventions used everywhere in this project:

    vx     forward is positive
    vy     left is positive
    omega  counter-clockwise (viewed from above) is positive

A positive motor power means "this wheel helps push the robot forward". If a
wheel spins the wrong way on the real robot, flip ``inverted`` for that
motor in config.yaml rather than changing the maths here.

            front
        FL /     \\ FR
          |  PAWS |
        BL \\     / BR
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from paws.hardware.motor import Motor

WHEELS = ("front_left", "front_right", "back_left", "back_right")


def clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def mix(vx: float, vy: float, omega: float) -> Tuple[Tuple[float, float, float, float], float]:
    """Turn a chassis command into four wheel powers.

    Returns ``(powers, scale)``. If any wheel would need more than full power
    all four are scaled down together, which keeps the direction of travel
    correct. ``scale`` is the factor that was applied (1.0 if none).
    """
    powers = (
        vx - vy - omega,  # front left
        vx + vy + omega,  # front right
        vx + vy - omega,  # back left
        vx - vy + omega,  # back right
    )
    biggest = max(abs(p) for p in powers)
    scale = 1.0 / biggest if biggest > 1.0 else 1.0
    return tuple(p * scale for p in powers), scale  # type: ignore[return-value]


class XDrive:
    def __init__(self, motors: Dict[str, Motor], max_power: float = 1.0) -> None:
        missing = [w for w in WHEELS if w not in motors]
        if missing:
            raise ValueError(f"Missing drive motors: {missing}")
        self.motors = motors
        self.max_power = clamp(max_power, 0.0, 1.0)
        # Chassis command actually being applied after scaling, each -1..1.
        self.applied: Tuple[float, float, float] = (0.0, 0.0, 0.0)

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> "XDrive":
        motors = {
            name: Motor.from_config(
                name,
                cfg["motors"][name],
                pwm_frequency=cfg.get("pwm_frequency", 1000),
                brake=cfg.get("brake", False),
            )
            for name in WHEELS
        }
        return cls(motors, max_power=cfg.get("max_power", 1.0))

    def drive(self, vx: float, vy: float, omega: float) -> None:
        vx, vy, omega = clamp(vx), clamp(vy), clamp(omega)
        powers, scale = mix(vx, vy, omega)
        for name, power in zip(WHEELS, powers):
            self.motors[name].set(power * self.max_power)
        k = scale * self.max_power
        self.applied = (vx * k, vy * k, omega * k)

    def stop(self) -> None:
        for motor in self.motors.values():
            motor.stop()
        self.applied = (0.0, 0.0, 0.0)

    @property
    def moving(self) -> bool:
        return any(abs(v) > 1e-6 for v in self.applied)

    def wheel_powers(self) -> Dict[str, float]:
        return {name: round(self.motors[name].power, 3) for name in WHEELS}

    def close(self) -> None:
        for motor in self.motors.values():
            motor.close()
