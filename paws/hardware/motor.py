"""DC motor on a direction + PWM motor controller.

Each controller channel takes three signals from the Pi:

    IN1, IN2  digital pins that pick the direction
    PWM       duty cycle that sets the speed

    IN1=1 IN2=0  forward
    IN1=0 IN2=1  reverse
    IN1=0 IN2=0  coast
    IN1=1 IN2=1  brake
"""

from __future__ import annotations

from typing import Any, Dict

from gpiozero import DigitalOutputDevice, PWMOutputDevice


class Motor:
    def __init__(
        self,
        in1: int,
        in2: int,
        pwm: int,
        inverted: bool = False,
        pwm_frequency: int = 1000,
        brake: bool = False,
        name: str = "motor",
    ) -> None:
        self.name = name
        self.inverted = inverted
        self.brake = brake
        self._in1 = DigitalOutputDevice(in1)
        self._in2 = DigitalOutputDevice(in2)
        self._pwm = PWMOutputDevice(pwm, frequency=pwm_frequency)
        self._power = 0.0

    @classmethod
    def from_config(cls, name: str, cfg: Dict[str, Any], **kwargs: Any) -> "Motor":
        return cls(
            in1=cfg["in1"],
            in2=cfg["in2"],
            pwm=cfg["pwm"],
            inverted=bool(cfg.get("inverted", False)),
            name=name,
            **kwargs,
        )

    @property
    def power(self) -> float:
        """Last commanded power, -1 (full reverse) to 1 (full forward)."""
        return self._power

    def set(self, power: float) -> None:
        power = max(-1.0, min(1.0, float(power)))
        self._power = power
        if self.inverted:
            power = -power

        if power > 0:
            self._in2.off()
            self._in1.on()
            self._pwm.value = power
        elif power < 0:
            self._in1.off()
            self._in2.on()
            self._pwm.value = -power
        elif self.brake:
            self._in1.on()
            self._in2.on()
            self._pwm.value = 1.0
        else:
            self._pwm.value = 0.0
            self._in1.off()
            self._in2.off()

    def stop(self) -> None:
        self.set(0.0)

    def close(self) -> None:
        try:
            self._pwm.value = 0.0
            self._in1.off()
            self._in2.off()
        finally:
            for dev in (self._pwm, self._in1, self._in2):
                dev.close()
