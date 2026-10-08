"""Feeding schedule.

A schedule is a list of entries like "08:00 on weekdays, 2 portions". They
are saved to ``data/schedule.json`` so they survive a reboot. A background
thread wakes up a few times a minute and fires any entry whose time has
arrived.

Times use the Pi's local clock, so set the Pi's timezone (``sudo
raspi-config``) to match where the robot lives.

Days are numbered Monday=0 through Sunday=6. An empty list means every day.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)

TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def validate_entry(time: str, days: List[int], portions: int) -> None:
    if not TIME_RE.match(time or ""):
        raise ValueError("time must be 24-hour HH:MM, for example 07:30")
    if any((not isinstance(d, int)) or d < 0 or d > 6 for d in days):
        raise ValueError("days must be numbers from 0 (Monday) to 6 (Sunday)")
    if int(portions) < 1:
        raise ValueError("portions must be at least 1")


class FeedingScheduler:
    def __init__(
        self,
        path: Optional[str],
        on_feed: Callable[[int, Dict[str, Any]], Any],
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.path = Path(path) if path else None
        self.on_feed = on_feed
        self.clock = clock
        self._entries: List[Dict[str, Any]] = []
        self._fired: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._load()

    # ---- storage -----------------------------------------------------

    def _load(self) -> None:
        if self.path and self.path.is_file():
            try:
                self._entries = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                log.warning("Could not read %s, starting with an empty schedule", self.path)
                self._entries = []

    def _save(self) -> None:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._entries, indent=2), encoding="utf-8")

    # ---- editing -----------------------------------------------------

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            return sorted((dict(e) for e in self._entries), key=lambda e: e["time"])

    def add(self, time: str, portions: int = 1, days: Optional[List[int]] = None, label: str = "", enabled: bool = True) -> Dict[str, Any]:
        days = sorted(set(days or []))
        validate_entry(time, days, portions)
        entry = {
            "id": uuid.uuid4().hex[:8],
            "time": time,
            "days": days,
            "portions": int(portions),
            "label": label,
            "enabled": bool(enabled),
        }
        with self._lock:
            self._entries.append(entry)
            self._save()
        return dict(entry)

    def update(self, entry_id: str, **changes: Any) -> Optional[Dict[str, Any]]:
        with self._lock:
            for entry in self._entries:
                if entry["id"] == entry_id:
                    merged = {**entry, **{k: v for k, v in changes.items() if v is not None and k != "id"}}
                    merged["days"] = sorted(set(merged["days"]))
                    validate_entry(merged["time"], merged["days"], merged["portions"])
                    entry.update(merged)
                    self._save()
                    return dict(entry)
        return None

    def remove(self, entry_id: str) -> bool:
        with self._lock:
            before = len(self._entries)
            self._entries = [e for e in self._entries if e["id"] != entry_id]
            self._save()
            return len(self._entries) < before

    # ---- running -----------------------------------------------------

    @staticmethod
    def _matches(entry: Dict[str, Any], when: datetime) -> bool:
        if not entry.get("enabled", True):
            return False
        if entry["days"] and when.weekday() not in entry["days"]:
            return False
        return entry["time"] == when.strftime("%H:%M")

    def check(self, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Fire every entry due at ``now``. Each fires once per minute slot."""
        now = now or self.clock()
        stamp = now.strftime("%Y-%m-%d %H:%M")
        with self._lock:
            due = [dict(e) for e in self._entries if self._matches(e, now) and self._fired.get(e["id"]) != stamp]
            for entry in due:
                self._fired[entry["id"]] = stamp
        for entry in due:
            try:
                self.on_feed(entry["portions"], entry)
            except Exception:  # noqa: BLE001
                log.exception("Scheduled feeding failed")
        return due

    def next_feeding(self, now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        """The next entry that will fire, with its ISO timestamp."""
        now = now or self.clock()
        best: Optional[Dict[str, Any]] = None
        for entry in self.list():
            if not entry.get("enabled", True):
                continue
            hour, minute = (int(p) for p in entry["time"].split(":"))
            for offset in range(8):
                when = (now + timedelta(days=offset)).replace(hour=hour, minute=minute, second=0, microsecond=0)
                if when <= now or (entry["days"] and when.weekday() not in entry["days"]):
                    continue
                if best is None or when.isoformat() < best["at"]:
                    best = {"at": when.isoformat(), "id": entry["id"], "portions": entry["portions"], "label": entry["label"]}
                break
        return best

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="scheduler")
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.wait(15):
            self.check()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
