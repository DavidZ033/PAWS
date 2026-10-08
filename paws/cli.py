"""Command line tool. This is what you use over SSH.

    python -m paws serve            start the robot (normally run by systemd)
    python -m paws teleop           drive with the keyboard
    python -m paws status           print what the robot is doing
    python -m paws feed -n 2        dispense two portions
    python -m paws launch           throw a ball
    python -m paws --help           everything else

Apart from ``serve``, ``hwtest`` and ``download-model``, every command is a
small HTTP client of the running server. That means the same commands work
on the Pi itself (the default, localhost) and from a laptop on the same
WiFi: ``python -m paws --host 192.168.1.50 status``.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from paws import __version__

DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class ApiError(Exception):
    pass


class Client:
    """Minimal JSON-over-HTTP client using only the standard library."""

    def __init__(self, host: str, port: int, token: str = "", timeout: float = 5.0) -> None:
        self.base = f"http://{host}:{port}"
        self.token = token
        self.timeout = timeout

    def request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None, raw: bool = False) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("X-PAWS-Token", self.token)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = resp.read()
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read()).get("detail", exc.reason)
            except Exception:  # noqa: BLE001
                detail = exc.reason
            raise ApiError(f"{exc.code}: {detail}") from None
        except (urllib.error.URLError, OSError) as exc:
            raise ApiError(
                f"Cannot reach the PAWS server at {self.base} ({getattr(exc, 'reason', exc)}).\n"
                "Is it running? Start it with: python -m paws serve"
            ) from None
        return payload if raw else json.loads(payload)

    def get(self, path: str, **kw: Any) -> Any:
        return self.request("GET", path, **kw)

    def post(self, path: str, body: Optional[Dict[str, Any]] = None) -> Any:
        return self.request("POST", path, body if body is not None else {})


# ---- helpers ---------------------------------------------------------


def parse_days(text: str) -> List[int]:
    """'mon,wed,fri' or 'weekdays' or 'daily' into day numbers."""
    text = (text or "daily").strip().lower()
    if text in ("daily", "all", "every"):
        return []
    if text == "weekdays":
        return [0, 1, 2, 3, 4]
    if text == "weekends":
        return [5, 6]
    days = []
    for part in text.split(","):
        part = part.strip()[:3]
        if part not in DAY_NAMES:
            raise SystemExit(f"Unknown day '{part}'. Use: {', '.join(DAY_NAMES)}, daily, weekdays, weekends")
        days.append(DAY_NAMES.index(part))
    return sorted(set(days))


def format_days(days: List[int]) -> str:
    return "daily" if not days else ",".join(DAY_NAMES[d] for d in days)


def ago(timestamp: Optional[float]) -> str:
    if not timestamp:
        return "never"
    seconds = max(0, int(time.time() - timestamp))
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    return f"{seconds // 3600}h {seconds % 3600 // 60}m ago"


def parse_point(text: str) -> Dict[str, Any]:
    """'x,y' or 'x,y,heading_degrees' into a waypoint dict."""
    parts = [p for p in text.replace(" ", "").split(",") if p]
    if len(parts) not in (2, 3):
        raise SystemExit(f"Bad waypoint '{text}'. Use x,y or x,y,heading_degrees")
    point: Dict[str, Any] = {"x": float(parts[0]), "y": float(parts[1])}
    if len(parts) == 3:
        point["theta"] = math.radians(float(parts[2]))
    return point


# ---- commands --------------------------------------------------------


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    from paws.config import load_config
    from paws.robot import Robot
    from paws.server import create_app

    overrides: Dict[str, Any] = {}
    if args.simulate:
        overrides["robot"] = {"simulate": True}
    cfg = load_config(args.config, overrides)
    host = args.bind or cfg["server"]["host"]
    port = args.port if args.port_given else cfg["server"]["port"]
    robot = Robot(cfg)
    uvicorn.run(create_app(robot), host=host, port=port, log_level="info")


def cmd_status(args: argparse.Namespace) -> None:
    s = args.client.get("/api/status")
    if args.json:
        print(json.dumps(s, indent=2))
        return
    pose, nav, det = s["pose"], s["navigation"], s["detection"]
    print(f"{s['name']} v{s['version']}" + ("  [SIMULATION]" if s["simulated"] else ""))
    print(f"  mode       {s['mode']}  (up {int(s['uptime'])}s)")
    print(f"  pose       x={pose['x']:.2f} m  y={pose['y']:.2f} m  heading={pose['theta_deg']:.0f} deg")
    print(f"  drive      vx={s['drive']['vx']:+.2f}  vy={s['drive']['vy']:+.2f}  omega={s['drive']['omega']:+.2f}")
    if nav["active"]:
        print(f"  navigating waypoint {nav['waypoint_index'] + 1}/{nav['waypoint_count']}, {nav['distance_to_target']} m to go")
    else:
        print(f"  navigation {nav['state']}")
    print(f"  launcher   {'RUNNING' if s['launcher']['running'] else 'off'}")
    print(f"  feeder     {'busy' if s['feeder']['busy'] else 'idle'}, last fed {ago(s['feeder']['last_fed'])}")
    nxt = s["next_feeding"]
    print(f"  next meal  {nxt['at'].replace('T', ' ')[:16] + ' x' + str(nxt['portions']) if nxt else 'nothing scheduled'}")
    cam = s["camera"]
    print(f"  camera     {cam['backend'] if cam['available'] else 'unavailable: ' + str(cam['error'])}")
    if not det["available"]:
        print(f"  detection  unavailable: {det['reason']}")
    elif not det["enabled"]:
        print("  detection  off")
    else:
        seen = "dog in view" if det["dog_present"] else f"no dog in view, last seen {ago(det['last_seen'])}"
        print(f"  detection  {seen}")


def cmd_drive(args: argparse.Namespace) -> None:
    """Drive at a fixed command for a set time, then stop."""
    end = time.monotonic() + args.seconds
    body = {"vx": args.vx, "vy": args.vy, "omega": args.omega}
    try:
        while time.monotonic() < end:
            args.client.post("/api/drive", body)
            time.sleep(0.1)
    finally:
        args.client.post("/api/drive", {"vx": 0, "vy": 0, "omega": 0})
    print("done")


def cmd_stop(args: argparse.Namespace) -> None:
    args.client.post("/api/stop")
    print("stopped")


def cmd_launch(args: argparse.Namespace) -> None:
    if args.off:
        args.client.post("/api/launcher/stop")
        print("launcher off")
        return
    body = {k: v for k, v in (("power", args.power), ("duration", args.duration)) if v is not None}
    r = args.client.post("/api/launcher/launch", body)
    print(f"launching at {r['power']:.0%} for {r['duration']:.1f}s")


def cmd_feed(args: argparse.Namespace) -> None:
    r = args.client.post("/api/feeder/dispense", {"portions": args.portions})
    print(f"dispensing {r['portions']} portion(s)")


def cmd_goto(args: argparse.Namespace) -> None:
    body: Dict[str, Any] = {"x": args.x, "y": args.y}
    if args.heading is not None:
        body["theta"] = math.radians(args.heading)
    args.client.post("/api/nav/goto", body)
    print(f"driving to ({args.x}, {args.y})")
    if args.wait:
        wait_for_navigation(args.client)


def cmd_patrol(args: argparse.Namespace) -> None:
    points = [parse_point(p) for p in args.points]
    args.client.post("/api/nav/patrol", {"waypoints": points, "loops": args.loops})
    print(f"patrolling {len(points)} waypoint(s), " + ("until cancelled" if args.loops == 0 else f"{args.loops} loop(s)"))
    if args.wait:
        wait_for_navigation(args.client)


def wait_for_navigation(client: Client) -> None:
    try:
        while True:
            s = client.get("/api/status")
            nav, pose = s["navigation"], s["pose"]
            print(f"\r  x={pose['x']:+.2f} y={pose['y']:+.2f} heading={pose['theta_deg']:+.0f} deg   ", end="", flush=True)
            if not nav["active"]:
                print(f"\n{nav['state']}")
                return
            time.sleep(0.25)
    except KeyboardInterrupt:
        client.post("/api/nav/cancel")
        print("\ncancelled")


def cmd_cancel(args: argparse.Namespace) -> None:
    args.client.post("/api/nav/cancel")
    print("navigation cancelled")


def cmd_reset_pose(args: argparse.Namespace) -> None:
    args.client.post("/api/odometry/reset", {"x": args.x, "y": args.y, "theta": math.radians(args.heading)})
    print("pose reset")


def cmd_schedule(args: argparse.Namespace) -> None:
    c = args.client
    if args.action == "add":
        entry = c.post("/api/schedule", {
            "time": args.time, "portions": args.portions, "days": parse_days(args.days), "label": args.label,
        })
        print(f"added {entry['id']}: {entry['time']} {format_days(entry['days'])} x{entry['portions']}")
    elif args.action == "remove":
        c.request("DELETE", f"/api/schedule/{args.id}")
        print(f"removed {args.id}")
    elif args.action in ("enable", "disable"):
        c.request("PATCH", f"/api/schedule/{args.id}", {"enabled": args.action == "enable"})
        print(f"{args.action}d {args.id}")
    else:
        data = c.get("/api/schedule")
        if not data["entries"]:
            print("No feedings scheduled. Add one with: python -m paws schedule add 08:00")
            return
        print(f"{'ID':<10}{'TIME':<7}{'DAYS':<30}{'PORTIONS':<10}{'ON':<5}LABEL")
        for e in data["entries"]:
            print(f"{e['id']:<10}{e['time']:<7}{format_days(e['days']):<30}{e['portions']:<10}{'yes' if e['enabled'] else 'no':<5}{e['label']}")
        if data["next"]:
            print(f"next: {data['next']['at'].replace('T', ' ')[:16]}")


def cmd_events(args: argparse.Namespace) -> None:
    for e in args.client.get(f"/api/events?limit={args.limit}")["events"]:
        stamp = time.strftime("%m-%d %H:%M:%S", time.localtime(e["time"]))
        photo = "  [snapshot]" if e.get("snapshot") else ""
        print(f"{e['id']:>5}  {stamp}  {e['type']:<13} {e['message']}{photo}")


def cmd_snapshot(args: argparse.Namespace) -> None:
    path = f"/api/events/{args.event}/snapshot" if args.event else "/api/camera/snapshot"
    data = args.client.get(path, raw=True)
    with open(args.output, "wb") as fh:
        fh.write(data)
    print(f"saved {args.output} ({len(data) // 1024} kB)")


def cmd_detection(args: argparse.Namespace) -> None:
    r = args.client.post("/api/detection", {"enabled": args.state == "on"})
    print(f"detection {'on' if r['enabled'] else 'off'}" + ("" if r["available"] else f" (unavailable: {r['reason']})"))


def cmd_download_model(args: argparse.Namespace) -> None:
    from paws.config import load_config
    from paws.detection import download_model

    cfg = load_config(args.config)
    name = args.model or cfg["detection"]["model"]
    print(f"Fetching dog detection model into '{cfg['detection']['model_dir']}'")
    download_model(cfg["detection"]["model_dir"], name, force=args.force)
    print("done")


def cmd_hwtest(args: argparse.Namespace) -> None:
    """Exercise each part in turn, talking to the hardware directly."""
    from paws.config import load_config
    from paws.robot import Robot

    cfg = load_config(args.config, {"camera": {"enabled": False}, "detection": {"enabled": False}})
    print("Hardware test. Stop the server first (sudo systemctl stop paws).")
    print("PUT THE ROBOT ON BLOCKS so the wheels are off the ground.")
    if not args.yes and input("Type 'yes' to continue: ").strip().lower() != "yes":
        return
    robot = Robot(cfg, persist=False)
    try:
        for name, motor in robot.drivetrain.motors.items():
            print(f"  {name}: forward", end="", flush=True)
            motor.set(args.power)
            time.sleep(1)
            print(", reverse", end="", flush=True)
            motor.set(-args.power)
            time.sleep(1)
            motor.stop()
            print(", ok")
            time.sleep(0.3)
        print("  Every wheel should have pushed the robot FORWARD first. If one went")
        print("  backward first, set inverted: true for it in config.yaml.")
        for motor in robot.launcher.motors:
            print(f"  {motor.name}: spin", end="", flush=True)
            motor.set(args.power)
            time.sleep(1.5)
            motor.stop()
            print(", ok")
        print("  feeder: one portion")
        robot.feeder.dispense(1, wait=True)
        print("  encoders: push the robot around by hand for 5 seconds")
        for _ in range(10):
            time.sleep(0.5)
            robot.odometry.update(0.5)
            pose = robot.odometry.pose
            print(f"    enc1={robot.enc1.ticks:>7}  enc2={robot.enc2.ticks:>7}  x={pose.x:+.3f} m  y={pose.y:+.3f} m")
        print("  Pushing forward should raise x, pushing left should raise y.")
        print("  If one goes the wrong way, set inverted: true for that encoder.")
    finally:
        robot.shutdown()


def cmd_teleop(args: argparse.Namespace) -> None:
    import curses

    client: Client = args.client
    client.get("/api/status")  # fail early with a clear message if unreachable

    keys = {
        ord("w"): (1, 0, 0), ord("s"): (-1, 0, 0),
        ord("a"): (0, 1, 0), ord("d"): (0, -1, 0),
        ord("q"): (0, 0, 1), ord("e"): (0, 0, -1),
    }

    def run(screen: Any) -> None:
        curses.curs_set(0)
        screen.nodelay(True)
        speed = args.speed
        direction = (0, 0, 0)
        last_key = 0.0
        note = ""
        status: Dict[str, Any] = {}
        tick = 0
        while True:
            # Drain every key pressed since the last pass.
            while True:
                key = screen.getch()
                if key == -1:
                    break
                if key in (ord("x"), 27):
                    return
                if key in keys:
                    direction, last_key = keys[key], time.monotonic()
                elif key == ord(" "):
                    direction = (0, 0, 0)
                    client.post("/api/stop")
                    note = "STOP"
                elif key in (ord("+"), ord("=")):
                    speed = min(1.0, round(speed + 0.1, 1))
                elif key in (ord("-"), ord("_")):
                    speed = max(0.1, round(speed - 0.1, 1))
                elif key == ord("f"):
                    try:
                        client.post("/api/feeder/dispense", {"portions": 1})
                        note = "fed 1 portion"
                    except ApiError as exc:
                        note = str(exc)
                elif key == ord("l"):
                    client.post("/api/launcher/launch")
                    note = "launching"
                elif key == ord("0"):
                    client.post("/api/odometry/reset")
                    note = "pose reset"

            # A terminal only reports key presses, never releases. Treat a
            # key as held while its auto-repeat keeps arriving.
            if direction != (0, 0, 0) and time.monotonic() - last_key > args.hold:
                direction = (0, 0, 0)
                client.post("/api/drive", {"vx": 0, "vy": 0, "omega": 0})
            if direction != (0, 0, 0):
                fx, fy, fw = direction
                client.post("/api/drive", {"vx": fx * speed, "vy": fy * speed, "omega": fw * speed * 0.7})

            if tick % 4 == 0:
                status = client.get("/api/status")
            tick += 1

            screen.erase()
            lines = [
                f"PAWS teleop    speed {speed:.0%}" + ("    [SIMULATION]" if status.get("simulated") else ""),
                "",
                "  w/s  forward / back        q/e  turn left / right",
                "  a/d  slide left / right    +/-  speed",
                "  f    feed    l  launch     0    reset position",
                "  SPACE  emergency stop      x    quit",
                "",
            ]
            if status:
                p, det = status["pose"], status["detection"]
                lines += [
                    f"  position  x={p['x']:+.2f} m  y={p['y']:+.2f} m  heading={p['theta_deg']:+.0f} deg",
                    f"  launcher  {'RUNNING' if status['launcher']['running'] else 'off'}"
                    f"      feeder  {'busy' if status['feeder']['busy'] else 'idle'}",
                    f"  dog       {'IN VIEW' if det['dog_present'] else 'not in view'}",
                ]
            lines += ["", f"  {note}"]
            for row, text in enumerate(lines):
                try:
                    screen.addstr(row, 0, text)
                except curses.error:
                    pass
            screen.refresh()
            time.sleep(0.08)

    try:
        curses.wrapper(run)
    finally:
        try:
            client.post("/api/drive", {"vx": 0, "vy": 0, "omega": 0})
        except ApiError:
            pass


# ---- argument parsing ------------------------------------------------


class _PortAction(argparse.Action):
    def __call__(self, parser: Any, namespace: Any, values: Any, option_string: Any = None) -> None:
        namespace.port = values
        namespace.port_given = True


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="paws", description="PAWS robot command line tool")
    p.add_argument("--version", action="version", version=f"paws {__version__}")
    p.add_argument("--host", default="localhost", help="robot address (default: localhost)")
    p.add_argument("--port", type=int, default=8000, action=_PortAction, help="server port (default: 8000)")
    p.add_argument("--token", default="", help="API token, if one is set in config.yaml")
    p.add_argument("--config", default=None, help="path to config.yaml")
    p.set_defaults(port_given=False)
    sub = p.add_subparsers(dest="command", metavar="command")

    s = sub.add_parser("serve", help="start the robot server")
    s.add_argument("--simulate", action="store_true", help="run without hardware")
    s.add_argument("--bind", default=None, help="address to listen on (default from config)")
    s.set_defaults(func=cmd_serve, local=True)

    s = sub.add_parser("teleop", help="drive with the keyboard")
    s.add_argument("--speed", type=float, default=0.5, help="starting speed 0..1")
    s.add_argument("--hold", type=float, default=0.6, help="seconds a key press keeps the robot moving")
    s.set_defaults(func=cmd_teleop)

    s = sub.add_parser("status", help="show what the robot is doing")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("drive", help="drive at a fixed command for a few seconds")
    s.add_argument("--vx", type=float, default=0.0, help="forward (+) / back (-), -1..1")
    s.add_argument("--vy", type=float, default=0.0, help="left (+) / right (-), -1..1")
    s.add_argument("--omega", type=float, default=0.0, help="counter-clockwise (+), -1..1")
    s.add_argument("--seconds", type=float, default=1.0)
    s.set_defaults(func=cmd_drive)

    sub.add_parser("stop", help="emergency stop").set_defaults(func=cmd_stop)

    s = sub.add_parser("launch", help="throw a ball")
    s.add_argument("--power", type=float, default=None, help="0..1")
    s.add_argument("--duration", type=float, default=None, help="seconds")
    s.add_argument("--off", action="store_true", help="stop the launcher now")
    s.set_defaults(func=cmd_launch)

    s = sub.add_parser("feed", help="dispense food")
    s.add_argument("-n", "--portions", type=int, default=1)
    s.set_defaults(func=cmd_feed)

    s = sub.add_parser("goto", help="drive to a point (metres from the start pose)")
    s.add_argument("x", type=float)
    s.add_argument("y", type=float)
    s.add_argument("--heading", type=float, default=None, help="final heading in degrees")
    s.add_argument("--wait", action="store_true", help="show progress until it arrives")
    s.set_defaults(func=cmd_goto)

    s = sub.add_parser("patrol", help="visit waypoints in order, e.g. 1,0 1,1 0,0")
    s.add_argument("points", nargs="+", help="x,y or x,y,heading_degrees")
    s.add_argument("--loops", type=int, default=1, help="0 = repeat until cancelled")
    s.add_argument("--wait", action="store_true")
    s.set_defaults(func=cmd_patrol)

    sub.add_parser("cancel", help="cancel navigation").set_defaults(func=cmd_cancel)

    s = sub.add_parser("reset-pose", help="declare where the robot currently is")
    s.add_argument("--x", type=float, default=0.0)
    s.add_argument("--y", type=float, default=0.0)
    s.add_argument("--heading", type=float, default=0.0, help="degrees")
    s.set_defaults(func=cmd_reset_pose)

    s = sub.add_parser("schedule", help="view or edit the feeding schedule")
    s.set_defaults(func=cmd_schedule, action="list")
    ssub = s.add_subparsers(dest="action", metavar="action")
    ssub.add_parser("list", help="show the schedule")
    a = ssub.add_parser("add", help="add a feeding, e.g. add 08:00 --days weekdays -n 2")
    a.add_argument("time", help="24-hour HH:MM")
    a.add_argument("-n", "--portions", type=int, default=1)
    a.add_argument("--days", default="daily", help="daily, weekdays, weekends or mon,wed,fri")
    a.add_argument("--label", default="")
    for name in ("remove", "enable", "disable"):
        ssub.add_parser(name, help=f"{name} an entry").add_argument("id")

    s = sub.add_parser("events", help="show recent events")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=cmd_events)

    s = sub.add_parser("snapshot", help="save a camera frame to a file")
    s.add_argument("-o", "--output", default="snapshot.jpg")
    s.add_argument("--event", type=int, default=None, help="fetch the snapshot saved with this event id")
    s.set_defaults(func=cmd_snapshot)

    s = sub.add_parser("detection", help="turn dog detection on or off")
    s.add_argument("state", choices=["on", "off"])
    s.set_defaults(func=cmd_detection)

    s = sub.add_parser("download-model", help="download the dog detection model")
    s.add_argument("--model", default=None, help="yolox_tiny or yolox_nano (default from config)")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_download_model, local=True)

    s = sub.add_parser("hwtest", help="test each motor, the servo and the encoders")
    s.add_argument("--power", type=float, default=0.3)
    s.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    s.set_defaults(func=cmd_hwtest, local=True)

    return p


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not getattr(args, "local", False):
        args.client = Client(args.host, args.port, args.token)
    try:
        args.func(args)
    except ApiError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
