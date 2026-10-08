"""Configuration loading.

Every tunable number and every GPIO pin lives in ``config.yaml``. The values
in ``DEFAULTS`` below are used for anything the YAML file leaves out, so a
partial config file is fine.

All pin numbers are BCM (GPIO) numbers, not physical header positions.
All distances are metres, all angles are radians, all times are seconds.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

DEFAULTS: Dict[str, Any] = {
    "robot": {
        "name": "PAWS",
        # "auto" simulates when not running on a Raspberry Pi.
        "simulate": "auto",
        "loop_hz": 50,
        "data_dir": "data",
    },
    "server": {
        "host": "0.0.0.0",
        "port": 8000,
        # Optional shared secret. Empty string disables the check.
        "token": "",
    },
    "drive": {
        "pwm_frequency": 1000,
        "max_power": 1.0,
        # Motors stop if no drive command arrives within this many seconds.
        "watchdog_timeout": 0.5,
        # False = coast when stopped, True = short the motor to brake.
        "brake": False,
        # Rough top speeds at full power. Used by the simulator and by the
        # "commanded" heading estimate. Measure and adjust on the real robot.
        "max_speed": 0.8,
        "max_turn_rate": 3.0,
        "motors": {
            "front_left": {"in1": 17, "in2": 27, "pwm": 22, "inverted": False},
            "front_right": {"in1": 23, "in2": 24, "pwm": 25, "inverted": False},
            "back_left": {"in1": 5, "in2": 6, "pwm": 13, "inverted": False},
            "back_right": {"in1": 16, "in2": 20, "pwm": 21, "inverted": False},
        },
    },
    "encoders": {
        # Steps gpiozero counts per wheel revolution (one per full quadrature
        # cycle). A REV Through Bore Encoder gives 2048.
        "ticks_per_rev": 2048,
        "wheel_diameter": 0.06,
        "enc1": {"a": 10, "b": 9, "inverted": False},
        "enc2": {"a": 11, "b": 4, "inverted": False},
    },
    "odometry": {
        # "perpendicular": enc1 rolls forward/back, enc2 rolls sideways.
        # "parallel": enc1 is the left wheel, enc2 the right, both roll forward.
        "layout": "perpendicular",
        # perpendicular layout only. "commanded" integrates the turn command,
        # "none" assumes the robot never rotates.
        "heading_source": "commanded",
        # perpendicular layout: how far enc1 sits to the LEFT of the robot
        # centre and how far enc2 sits FORWARD of it.
        "enc1_offset": 0.0,
        "enc2_offset": 0.0,
        # parallel layout: distance between the two tracking wheels.
        "track_width": 0.20,
    },
    "launcher": {
        "pwm_frequency": 1000,
        "default_power": 0.8,
        "default_duration": 3.0,
        # Hard cap on a single spin, whatever the caller asks for.
        "max_run_time": 10.0,
        "motors": {
            "left": {"in1": 7, "in2": 8, "pwm": 12, "inverted": False},
            "right": {"in1": 14, "in2": 15, "pwm": 18, "inverted": True},
        },
    },
    "feeder": {
        "pin": 19,
        # "positional": swing open, wait, swing closed.
        # "continuous": spin for a fixed time per portion.
        "mode": "positional",
        "min_pulse_ms": 0.5,
        "max_pulse_ms": 2.5,
        # Servo positions on a -1..1 scale.
        "closed_position": -1.0,
        "open_position": 0.0,
        "open_time": 1.0,
        "pause_between_portions": 0.5,
        "continuous_speed": 0.5,
        "max_portions": 5,
        # Stop sending pulses when idle so the servo does not buzz.
        "detach_when_idle": True,
    },
    "camera": {
        "enabled": True,
        # "auto", "picamera2", "opencv" or "synthetic"
        "backend": "auto",
        "width": 640,
        "height": 480,
        "fps": 15,
        "jpeg_quality": 70,
        # 0, 90, 180 or 270 degrees clockwise.
        "rotate": 0,
        # Device index for the "opencv" backend (USB webcam).
        "device": 0,
    },
    "detection": {
        "enabled": True,
        "model_dir": "models",
        # "yolox_tiny" (more accurate) or "yolox_nano" (faster)
        "model": "yolox_tiny",
        "labels": ["dog"],
        "confidence": 0.4,
        "interval": 1.0,
        "input_size": 416,
        # Minimum seconds between two "dog detected" events.
        "event_cooldown": 60,
        # Seconds without a sighting before the dog counts as gone.
        "lost_after": 5,
    },
    "navigation": {
        "kp_linear": 1.5,
        "kp_angular": 1.5,
        "max_power": 0.5,
        "max_turn_power": 0.4,
        # Smallest power that actually moves the robot.
        "min_power": 0.12,
        "position_tolerance": 0.05,
        "heading_tolerance": 0.1,
        # Seconds allowed per waypoint.
        "timeout": 30,
    },
}


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Return ``base`` with ``override`` laid on top, recursing into dicts."""
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def find_config_file(path: Optional[str] = None) -> Optional[Path]:
    """Explicit path, then $PAWS_CONFIG, then ./config.yaml."""
    for candidate in (path, os.environ.get("PAWS_CONFIG"), "config.yaml"):
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    if path:
        raise FileNotFoundError(f"Config file not found: {path}")
    return None


def load_config(path: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = copy.deepcopy(DEFAULTS)
    file = find_config_file(path)
    if file is not None:
        with open(file, "r", encoding="utf-8") as fh:
            cfg = deep_merge(cfg, yaml.safe_load(fh) or {})
        cfg["_file"] = str(file)
    if overrides:
        cfg = deep_merge(cfg, overrides)
    return cfg


def is_raspberry_pi() -> bool:
    try:
        with open("/proc/device-tree/model", "r", encoding="utf-8", errors="ignore") as fh:
            return "raspberry pi" in fh.read().lower()
    except OSError:
        return False


def should_simulate(cfg: Dict[str, Any]) -> bool:
    value = cfg["robot"].get("simulate", "auto")
    if isinstance(value, bool):
        return value
    if str(value).lower() in ("true", "yes", "1"):
        return True
    if str(value).lower() in ("false", "no", "0"):
        return False
    return not is_raspberry_pi()
