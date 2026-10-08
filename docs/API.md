# API reference

The robot listens on port 8000. A live, clickable version of this page is served by the robot itself at `http://<robot ip>:8000/docs`.

## Conventions

* All bodies are JSON.
* Drive values run from -1 to 1.
  * `vx`: forward is positive
  * `vy`: left is positive
  * `omega`: counter-clockwise (seen from above) is positive
* Positions are metres from where the robot started. x is forward, y is left. Headings are radians, counter-clockwise.
* Times in events are Unix seconds.
* If `server.token` is set in `config.yaml`, send it as an `X-PAWS-Token` header or a `?token=` query parameter.

## REST endpoints

### Status

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/status` | Everything about the robot's current state |

### Driving

| Method | Path | Body | Description |
| --- | --- | --- | --- |
| POST | `/api/drive` | `{"vx": 0.5, "vy": 0, "omega": 0}` | Manual drive. Expires after 0.5 s, so re-send at 5 Hz or faster. Cancels navigation. |
| POST | `/api/stop` | none | Emergency stop: wheels, launcher and navigation |

### Launcher and feeder

| Method | Path | Body | Description |
| --- | --- | --- | --- |
| POST | `/api/launcher/launch` | `{"power": 0.8, "duration": 3}` (both optional) | Spin the flywheels, then stop automatically |
| POST | `/api/launcher/stop` | none | Stop the flywheels now |
| POST | `/api/feeder/dispense` | `{"portions": 1}` | Dispense food. Returns 409 if the feeder is already busy. |

### Feeding schedule

| Method | Path | Body | Description |
| --- | --- | --- | --- |
| GET | `/api/schedule` | | All entries plus the next one due |
| POST | `/api/schedule` | `{"time": "08:00", "portions": 2, "days": [0,1,2,3,4], "label": "Breakfast"}` | Add an entry |
| PATCH | `/api/schedule/{id}` | any subset of the fields, for example `{"enabled": false}` | Change an entry |
| DELETE | `/api/schedule/{id}` | | Remove an entry |

`time` is 24-hour `HH:MM` on the Pi's clock. `days` uses 0 for Monday through 6 for Sunday; an empty list means every day.

### Navigation

| Method | Path | Body | Description |
| --- | --- | --- | --- |
| POST | `/api/nav/goto` | `{"x": 1.0, "y": 0.5, "theta": 1.57}` (`theta` optional) | Drive to a point |
| POST | `/api/nav/patrol` | `{"waypoints": [{"x": 1, "y": 0}, {"x": 0, "y": 0}], "loops": 2}` | Visit points in order. `loops: 0` repeats until cancelled. |
| POST | `/api/nav/cancel` | none | Stop navigating |
| POST | `/api/odometry/reset` | `{"x": 0, "y": 0, "theta": 0}` (optional) | Declare the robot's current spot to be this pose |

### Events

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/events?limit=50&since=0&type=dog_detected` | Recent events, oldest first. All parameters optional. |
| GET | `/api/events/{id}/snapshot` | The JPEG saved with an event |

Event types: `system`, `feed`, `feed_skipped`, `launch`, `navigation`, `dog_detected`.

### Camera and detection

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/camera/snapshot` | One JPEG frame |
| GET | `/api/camera/stream` | Live MJPEG video. Works directly in a browser or an `<img>` tag. |
| POST | `/api/detection` with `{"enabled": true}` | Turn dog detection on or off |

## WebSocket

Connect to `ws://<robot ip>:8000/ws` (add `?token=...` if a token is set).

**The robot sends:**

```json
{"type": "status", "data": { ...same as GET /api/status... }}
{"type": "event",  "data": {"id": 12, "time": 1791492272.5, "type": "dog_detected", "message": "Dog spotted (91% confident)", "snapshot": "event_000012.jpg", "data": {}}}
{"type": "ack",    "action": "feed", "ok": true}
{"type": "pong"}
{"type": "error",  "message": "..."}
```

Status arrives five times a second. Events arrive as they happen.

**You send:**

```json
{"type": "drive", "vx": 0.5, "vy": 0, "omega": 0}
{"type": "stop"}
{"type": "feed", "portions": 1}
{"type": "launch", "power": 0.8, "duration": 3}
{"type": "launcher_stop"}
{"type": "ping"}
```

Drive messages follow the same rule as `POST /api/drive`: keep sending them while you want the robot to move. If the socket that was driving disconnects, the wheels stop immediately.

## Example status

```json
{
  "name": "PAWS",
  "version": "1.0.0",
  "simulated": false,
  "uptime": 124.1,
  "mode": "manual",
  "drive": {"vx": 0, "vy": 0, "omega": 0, "wheels": {"front_left": 0, "front_right": 0, "back_left": 0, "back_right": 0}},
  "pose": {"x": 0.42, "y": -0.1, "theta": 0.0, "theta_deg": 0.0},
  "encoders": {"enc1": 4563, "enc2": -1087},
  "navigation": {"state": "idle", "active": false, "target": null, "waypoint_index": null, "waypoint_count": 0, "distance_to_target": null},
  "launcher": {"running": false, "power": 0, "last_launch": null},
  "feeder": {"busy": false, "last_fed": 1791492000.2, "total_portions": 3, "mode": "positional"},
  "next_feeding": {"at": "2026-10-09T08:00:00", "id": "41ee5847", "portions": 2, "label": "Breakfast"},
  "camera": {"available": true, "backend": "picamera2", "width": 640, "height": 480, "fps": 15, "error": null},
  "detection": {"enabled": true, "available": true, "reason": null, "dog_present": true, "confidence": 0.91, "box": [65, 263, 135, 85], "last_seen": 1791492272.5},
  "last_event_id": 12
}
```
