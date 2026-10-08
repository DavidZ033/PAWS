"""Hobby servo output (REV Smart Robot Servo or similar).

Position is on a -1..1 scale: -1 is the shortest pulse, 1 the longest. For a
servo in continuous rotation mode the same number is a speed instead.
"""

from __future__ import annotations

from typing import Optional

from gpiozero import Servo


class ServoOutput:
    def __init__(self, pin: int, min_pulse_ms: float = 0.5, max_pulse_ms: float = 2.5) -> None:
        self._servo = Servo(
            pin,
            initial_value=None,
            min_pulse_width=min_pulse_ms / 1000.0,
            max_pulse_width=max_pulse_ms / 1000.0,
        )
        self._value: Optional[float] = None

    @property
    def value(self) -> Optional[float]:
        return self._value

    def set(self, value: float) -> None:
        value = max(-1.0, min(1.0, float(value)))
        self._value = value
        self._servo.value = value

    def detach(self) -> None:
        """Stop sending pulses. The servo goes limp and stops buzzing."""
        self._value = None
        self._servo.value = None

    def close(self) -> None:
        try:
            self._servo.value = None
        finally:
            self._servo.close()
