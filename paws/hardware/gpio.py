"""GPIO backend selection.

On the Pi we use gpiozero's default pin factory (lgpio on current Raspberry
Pi OS). In simulation we swap in gpiozero's mock factory, so the exact same
motor and servo code runs on a laptop without touching real pins.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def setup_gpio(simulate: bool) -> None:
    from gpiozero import Device

    if simulate:
        from gpiozero.pins.mock import MockFactory, MockPWMPin

        Device.pin_factory = MockFactory(pin_class=MockPWMPin)
        log.info("GPIO: simulated (mock pins)")
    else:
        log.info("GPIO: real hardware")
