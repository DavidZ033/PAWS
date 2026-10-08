"""Event log: a running history of what the robot did and saw.

Events are kept in memory for the API and appended to ``data/events.jsonl``
so the history survives a restart. Each event may point at a snapshot image
stored in ``data/snapshots``.
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional


class EventLog:
    def __init__(self, data_dir: str, max_events: int = 500, persist: bool = True) -> None:
        self.dir = Path(data_dir)
        self.snapshot_dir = self.dir / "snapshots"
        self.persist = persist
        self._file = self.dir / "events.jsonl"
        self._events: Deque[Dict[str, Any]] = deque(maxlen=max_events)
        self._lock = threading.Lock()
        self._next_id = 1
        if persist:
            self.snapshot_dir.mkdir(parents=True, exist_ok=True)
            self._load()

    def _load(self) -> None:
        if not self._file.is_file():
            return
        with open(self._file, "r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    self._events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        if self._events:
            self._next_id = self._events[-1]["id"] + 1

    @property
    def last_id(self) -> int:
        return self._next_id - 1

    def add(
        self,
        kind: str,
        message: str,
        data: Optional[Dict[str, Any]] = None,
        snapshot: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        """Record an event. ``snapshot`` is JPEG bytes to save alongside it."""
        with self._lock:
            event: Dict[str, Any] = {
                "id": self._next_id,
                "time": time.time(),
                "type": kind,
                "message": message,
                "data": data or {},
                "snapshot": None,
            }
            self._next_id += 1
            if snapshot and self.persist:
                name = f"event_{event['id']:06d}.jpg"
                (self.snapshot_dir / name).write_bytes(snapshot)
                event["snapshot"] = name
            self._events.append(event)
            if self.persist:
                with open(self._file, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(event) + "\n")
            return event

    def list(self, limit: int = 50, since_id: int = 0, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        """Events with id greater than ``since_id``, oldest first."""
        with self._lock:
            items = [e for e in self._events if e["id"] > since_id and (kind is None or e["type"] == kind)]
        return items[-limit:] if limit else items

    def snapshot_path(self, event_id: int) -> Optional[Path]:
        with self._lock:
            for event in self._events:
                if event["id"] == event_id and event.get("snapshot"):
                    path = self.snapshot_dir / event["snapshot"]
                    return path if path.is_file() else None
        return None
