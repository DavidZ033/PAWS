"""Thin wrappers around the physical parts: motors, encoders and the servo."""

from paws.hardware.gpio import setup_gpio
from paws.hardware.motor import Motor
from paws.hardware.encoder import Encoder
from paws.hardware.servo import ServoOutput

__all__ = ["setup_gpio", "Motor", "Encoder", "ServoOutput"]
