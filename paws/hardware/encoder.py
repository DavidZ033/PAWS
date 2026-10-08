"""Quadrature encoder on an unpowered omni tracking wheel.

The wheel is pressed against the floor and spins freely, so it measures how
far the robot really moved even when the drive wheels slip.

In simulation there is no encoder to read, so the physics model pushes
distance in through ``simulate_move``.
"""

from __future__ import annotations

import math
from typing import Any, Dict


class Encoder:
    def __init__(
        self,
        a: int,
        b: int,
        ticks_per_rev: float,
        wheel_diameter: float,
        inverted: bool = False,
        simulated: bool = False,
        name: str = "encoder",
    ) -> None:
        self.name = name
        self.inverted = inverted
        self.simulated = simulated
        self.metres_per_tick = math.pi * wheel_diameter / float(ticks_per_rev)
        self._offset = 0
        self._sim_ticks = 0.0
        self._device = None
        if not simulated:
            from gpiozero import RotaryEncoder

            # max_steps=0 means count without limit.
            self._device = RotaryEncoder(a, b, max_steps=0)

    @classmethod
    def from_config(cls, name: str, cfg: Dict[str, Any], shared: Dict[str, Any], simulated: bool) -> "Encoder":
        return cls(
            a=cfg["a"],
            b=cfg["b"],
            ticks_per_rev=shared["ticks_per_rev"],
            wheel_diameter=shared["wheel_diameter"],
            inverted=bool(cfg.get("inverted", False)),
            simulated=simulated,
            name=name,
        )

    @property
    def ticks(self) -> int:
        raw = self._sim_ticks if self.simulated else self._device.steps
        raw = int(round(raw)) - self._offset
        return -raw if self.inverted else raw

    @property
    def distance(self) -> float:
        """Metres rolled since the last reset."""
        return self.ticks * self.metres_per_tick

    def reset(self) -> None:
        raw = self._sim_ticks if self.simulated else self._device.steps
        self._offset = int(round(raw))

    def simulate_move(self, metres: float) -> None:
        """Simulation only: roll the wheel by ``metres``."""
        ticks = metres / self.metres_per_tick
        self._sim_ticks += -ticks if self.inverted else ticks

    def close(self) -> None:
        if self._device is not None:
            self._device.close()
