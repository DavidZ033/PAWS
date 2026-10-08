"""The Robot class ties every subsystem together.

Everything that controls PAWS (the web API, the phone app, the command line
tool) goes through this one object, so the safety rules live in one place:

* Drive commands expire. If nothing new arrives within the watchdog time
  the wheels stop, so losing WiFi cannot leave the robot driving.
* Any manual drive command cancels autonomous navigation.
* ``stop_all`` halts wheels, launcher and navigation at once.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from paws import __version__
from paws.camera import Camera
from paws.config import should_simulate
from paws.detection import DogDetector
from paws.drivetrain import XDrive
from paws.events import EventLog
from paws.feeder import Feeder
from paws.hardware import Encoder, setup_gpio
from paws.launcher import Launcher
from paws.navigation import Navigator, Waypoint
from paws.odometry import Odometry
from paws.scheduler import FeedingScheduler
from paws.sim import SimPhysics

log = logging.getLogger(__name__)


class Robot:
    def __init__(self, cfg: Dict[str, Any], persist: bool = True) -> None:
        self.cfg = cfg
        self.name = cfg["robot"].get("name", "PAWS")
        self.simulated = should_simulate(cfg)
        self.loop_hz = float(cfg["robot"].get("loop_hz", 50))
        self.watchdog_timeout = float(cfg["drive"].get("watchdog_timeout", 0.5))
        data_dir = Path(cfg["robot"].get("data_dir", "data"))

        setup_gpio(self.simulated)

        self.events = EventLog(str(data_dir), persist=persist)
        self.drivetrain = XDrive.from_config(cfg["drive"])
        enc_cfg = cfg["encoders"]
        self.enc1 = Encoder.from_config("enc1", enc_cfg["enc1"], enc_cfg, self.simulated)
        self.enc2 = Encoder.from_config("enc2", enc_cfg["enc2"], enc_cfg, self.simulated)
        max_turn_rate = float(cfg["drive"].get("max_turn_rate", 3.0))
        self.odometry = Odometry(self.enc1, self.enc2, cfg["odometry"], max_turn_rate)
        self.launcher = Launcher.from_config(cfg["launcher"])
        self.feeder = Feeder.from_config(cfg["feeder"])
        self.camera = Camera(cfg["camera"], self.simulated)
        self.detector = DogDetector(cfg["detection"], self.camera, self.events)
        self.navigator = Navigator(cfg["navigation"])
        self.scheduler = FeedingScheduler(
            str(data_dir / "schedule.json") if persist else None,
            on_feed=self._scheduled_feed,
        )
        self.sim: Optional[SimPhysics] = None
        if self.simulated:
            self.sim = SimPhysics(
                self.odometry, self.enc1, self.enc2,
                float(cfg["drive"].get("max_speed", 0.8)), max_turn_rate,
            )

        self._lock = threading.RLock()
        self._last_drive_cmd = 0.0
        self._nav_state = self.navigator.state
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._started_at = time.time()

    # ---- lifecycle ---------------------------------------------------

    def start(self) -> None:
        """Start the control loop and all background workers."""
        if self._running:
            return
        self._running = True
        self._started_at = time.time()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="control")
        self._thread.start()
        self.camera.start()
        self.detector.start()
        self.scheduler.start()
        self.events.add("system", f"{self.name} started" + (" (simulation)" if self.simulated else ""))
        log.info("%s started%s", self.name, " in SIMULATION mode" if self.simulated else "")

    def shutdown(self) -> None:
        """Stop everything and release the GPIO pins."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        self.scheduler.stop()
        self.detector.stop()
        self.camera.stop()
        self.navigator.cancel()
        self.launcher.close()
        self.drivetrain.stop()
        self.drivetrain.close()
        self.feeder.close()
        self.enc1.close()
        self.enc2.close()
        log.info("%s stopped", self.name)

    def _loop(self) -> None:
        period = 1.0 / self.loop_hz
        last = time.monotonic()
        while self._running:
            now = time.monotonic()
            try:
                self.step(now - last, now)
            except Exception:  # noqa: BLE001
                log.exception("Control loop error, stopping motors")
                self.drivetrain.stop()
            last = now
            time.sleep(max(0.0, period - (time.monotonic() - now)))

    def step(self, dt: float, now: Optional[float] = None) -> None:
        """One control tick: track position, steer, enforce the watchdog."""
        now = time.monotonic() if now is None else now
        with self._lock:
            if self.sim is not None:
                self.sim.step(self.drivetrain.applied, dt)
            pose = self.odometry.update(dt, omega_cmd=self.drivetrain.applied[2])

            command = self.navigator.update(pose, dt)
            if command is not None:
                self.drivetrain.drive(*command)
            elif self._nav_state == "running":
                # Navigation just finished or failed this tick.
                self.drivetrain.stop()
            elif self.drivetrain.moving and now - self._last_drive_cmd > self.watchdog_timeout:
                self.drivetrain.stop()

            self._sync_nav_state()

    def _sync_nav_state(self) -> None:
        """Log an event when navigation ends, however it ended."""
        if self.navigator.state != self._nav_state:
            previous, self._nav_state = self._nav_state, self.navigator.state
            if previous == "running":
                pose = self.odometry.pose.as_dict()
                self.events.add("navigation", f"Navigation {self._nav_state}", {"pose": pose})

    # ---- driving -----------------------------------------------------

    def drive(self, vx: float = 0.0, vy: float = 0.0, omega: float = 0.0) -> None:
        """Manual drive. Must be re-sent regularly or the watchdog stops it."""
        with self._lock:
            self.navigator.cancel()
            self._sync_nav_state()
            self._last_drive_cmd = time.monotonic()
            self.drivetrain.drive(vx, vy, omega)

    def stop_drive(self) -> None:
        with self._lock:
            self.navigator.cancel()
            self._sync_nav_state()
            self.drivetrain.stop()

    def stop_all(self) -> None:
        """Emergency stop: wheels, launcher and navigation."""
        self.stop_drive()
        self.launcher.stop()

    # ---- navigation --------------------------------------------------

    def goto(self, x: float, y: float, theta: Optional[float] = None) -> None:
        with self._lock:
            self.navigator.goto(x, y, theta)
            self._nav_state = self.navigator.state

    def patrol(self, waypoints: List[Dict[str, Any]], loops: int = 1) -> None:
        points = [Waypoint(float(w["x"]), float(w["y"]), w.get("theta")) for w in waypoints]
        with self._lock:
            self.navigator.patrol(points, loops)
            self._nav_state = self.navigator.state

    def cancel_navigation(self) -> None:
        self.stop_drive()

    def reset_pose(self, x: float = 0.0, y: float = 0.0, theta: float = 0.0) -> None:
        with self._lock:
            self.odometry.reset(x, y, theta)
            if self.sim is not None:
                self.sim.true_pose = self.odometry.pose

    # ---- launcher and feeder -----------------------------------------

    def launch(self, power: Optional[float] = None, duration: Optional[float] = None) -> Dict[str, float]:
        result = self.launcher.launch(power, duration)
        self.events.add("launch", f"Ball launcher fired at {result['power']:.0%} power", result)
        return result

    def feed(self, portions: int = 1, source: str = "manual", label: str = "") -> bool:
        portions = self.feeder.clamp_portions(portions)
        started = self.feeder.dispense(portions)
        if started:
            what = f"{portions} portion" + ("s" if portions != 1 else "")
            suffix = f" ({label})" if label else ""
            self.events.add("feed", f"Dispensed {what}, {source}{suffix}", {"portions": portions, "source": source})
        else:
            self.events.add("feed_skipped", f"Feeder busy, skipped a {source} feeding", {"portions": portions, "source": source})
        return started

    def _scheduled_feed(self, portions: int, entry: Dict[str, Any]) -> None:
        self.feed(portions, source="scheduled", label=entry.get("label", ""))

    # ---- reporting ---------------------------------------------------

    def status(self) -> Dict[str, Any]:
        vx, vy, omega = self.drivetrain.applied
        return {
            "name": self.name,
            "version": __version__,
            "simulated": self.simulated,
            "time": time.time(),
            "uptime": round(time.time() - self._started_at, 1),
            "mode": "auto" if self.navigator.active else "manual",
            "drive": {
                "vx": round(vx, 3),
                "vy": round(vy, 3),
                "omega": round(omega, 3),
                "wheels": self.drivetrain.wheel_powers(),
            },
            "pose": self.odometry.pose.as_dict(),
            "encoders": {"enc1": self.enc1.ticks, "enc2": self.enc2.ticks},
            "navigation": self.navigator.status(),
            "launcher": self.launcher.status(),
            "feeder": self.feeder.status(),
            "next_feeding": self.scheduler.next_feeding(),
            "camera": self.camera.status(),
            "detection": self.detector.status(),
            "last_event_id": self.events.last_id,
        }
