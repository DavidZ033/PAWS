"""HTTP and WebSocket server.

This is the single doorway to the robot. The phone app and the command line
tool are both just clients of this API.

    REST   /api/...   one-off actions and queries (feed, launch, schedule)
    WS     /ws        live driving and a 5 Hz status feed
    MJPEG  /api/camera/stream   live video

Interactive documentation is generated automatically at /docs.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from paws import __version__
from paws.robot import Robot

log = logging.getLogger(__name__)

STATUS_HZ = 5


class DriveCommand(BaseModel):
    vx: float = Field(0.0, ge=-1, le=1, description="Forward (+) / backward (-)")
    vy: float = Field(0.0, ge=-1, le=1, description="Left (+) / right (-)")
    omega: float = Field(0.0, ge=-1, le=1, description="Counter-clockwise (+) / clockwise (-)")


class LaunchCommand(BaseModel):
    power: Optional[float] = Field(None, ge=0, le=1)
    duration: Optional[float] = Field(None, gt=0, description="Seconds")


class FeedCommand(BaseModel):
    portions: int = Field(1, ge=1)


class ScheduleEntryIn(BaseModel):
    time: str = Field(..., description="24-hour HH:MM")
    portions: int = Field(1, ge=1)
    days: List[int] = Field(default_factory=list, description="0=Monday .. 6=Sunday, empty = every day")
    label: str = ""
    enabled: bool = True


class ScheduleEntryPatch(BaseModel):
    time: Optional[str] = None
    portions: Optional[int] = Field(None, ge=1)
    days: Optional[List[int]] = None
    label: Optional[str] = None
    enabled: Optional[bool] = None


class WaypointIn(BaseModel):
    x: float
    y: float
    theta: Optional[float] = Field(None, description="Heading in radians, omit to keep current")


class PatrolCommand(BaseModel):
    waypoints: List[WaypointIn] = Field(..., min_length=1)
    loops: int = Field(1, ge=0, description="0 = repeat until cancelled")


class PoseIn(BaseModel):
    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0


class DetectionSettings(BaseModel):
    enabled: bool


def create_app(robot: Robot) -> FastAPI:
    token = robot.cfg["server"].get("token") or ""

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        robot.start()
        try:
            yield
        finally:
            robot.shutdown()

    app = FastAPI(title=f"{robot.name} robot API", version=__version__, lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.state.robot = robot

    def check_token(
        x_paws_token: Optional[str] = Header(None),
        token_query: Optional[str] = Query(None, alias="token"),
    ) -> None:
        if token and token not in (x_paws_token, token_query):
            raise HTTPException(status_code=401, detail="Missing or wrong token")

    api = APIRouter(prefix="/api", dependencies=[Depends(check_token)])

    @app.get("/")
    def root() -> Dict[str, Any]:
        return {"name": robot.name, "version": __version__, "docs": "/docs", "status": "/api/status"}

    # ---- status ------------------------------------------------------

    @api.get("/status", summary="Full robot state")
    def status() -> Dict[str, Any]:
        return robot.status()

    # ---- driving -----------------------------------------------------

    @api.post("/drive", summary="Manual drive (re-send at 5 Hz or faster)")
    def drive(cmd: DriveCommand) -> Dict[str, Any]:
        robot.drive(cmd.vx, cmd.vy, cmd.omega)
        return {"ok": True}

    @api.post("/stop", summary="Emergency stop: wheels, launcher, navigation")
    def stop() -> Dict[str, Any]:
        robot.stop_all()
        return {"ok": True}

    # ---- launcher and feeder -----------------------------------------

    @api.post("/launcher/launch", summary="Spin the ball launcher")
    def launch(cmd: Optional[LaunchCommand] = None) -> Dict[str, Any]:
        cmd = cmd or LaunchCommand()
        return {"ok": True, **robot.launch(cmd.power, cmd.duration)}

    @api.post("/launcher/stop")
    def launcher_stop() -> Dict[str, Any]:
        robot.launcher.stop()
        return {"ok": True}

    @api.post("/feeder/dispense", summary="Dispense food now")
    def feed(cmd: Optional[FeedCommand] = None) -> Dict[str, Any]:
        cmd = cmd or FeedCommand()
        if not robot.feed(cmd.portions, source="manual"):
            raise HTTPException(status_code=409, detail="Feeder is busy")
        return {"ok": True, "portions": robot.feeder.clamp_portions(cmd.portions)}

    # ---- feeding schedule --------------------------------------------

    @api.get("/schedule")
    def schedule_list() -> Dict[str, Any]:
        return {"entries": robot.scheduler.list(), "next": robot.scheduler.next_feeding()}

    @api.post("/schedule", status_code=201)
    def schedule_add(entry: ScheduleEntryIn) -> Dict[str, Any]:
        try:
            return robot.scheduler.add(entry.time, entry.portions, entry.days, entry.label, entry.enabled)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @api.patch("/schedule/{entry_id}")
    def schedule_update(entry_id: str, patch: ScheduleEntryPatch) -> Dict[str, Any]:
        try:
            updated = robot.scheduler.update(entry_id, **patch.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        if updated is None:
            raise HTTPException(status_code=404, detail="No such schedule entry")
        return updated

    @api.delete("/schedule/{entry_id}")
    def schedule_remove(entry_id: str) -> Dict[str, Any]:
        if not robot.scheduler.remove(entry_id):
            raise HTTPException(status_code=404, detail="No such schedule entry")
        return {"ok": True}

    # ---- navigation --------------------------------------------------

    @api.post("/nav/goto", summary="Drive to a point")
    def nav_goto(target: WaypointIn) -> Dict[str, Any]:
        robot.goto(target.x, target.y, target.theta)
        return {"ok": True, "navigation": robot.navigator.status()}

    @api.post("/nav/patrol", summary="Visit a list of points in order")
    def nav_patrol(cmd: PatrolCommand) -> Dict[str, Any]:
        robot.patrol([w.model_dump() for w in cmd.waypoints], cmd.loops)
        return {"ok": True, "navigation": robot.navigator.status()}

    @api.post("/nav/cancel")
    def nav_cancel() -> Dict[str, Any]:
        robot.cancel_navigation()
        return {"ok": True}

    @api.post("/odometry/reset", summary="Declare the current spot to be this pose")
    def odometry_reset(pose: Optional[PoseIn] = None) -> Dict[str, Any]:
        pose = pose or PoseIn()
        robot.reset_pose(pose.x, pose.y, pose.theta)
        return {"ok": True, "pose": robot.odometry.pose.as_dict()}

    # ---- events ------------------------------------------------------

    @api.get("/events", summary="Recent events, oldest first")
    def events(limit: int = 50, since: int = 0, type: Optional[str] = None) -> Dict[str, Any]:
        return {"events": robot.events.list(limit=limit, since_id=since, kind=type)}

    @api.get("/events/{event_id}/snapshot")
    def event_snapshot(event_id: int) -> FileResponse:
        path = robot.events.snapshot_path(event_id)
        if path is None:
            raise HTTPException(status_code=404, detail="No snapshot for that event")
        return FileResponse(path, media_type="image/jpeg")

    # ---- camera and detection ----------------------------------------

    @api.get("/camera/snapshot", summary="One JPEG frame")
    def camera_snapshot() -> Response:
        _, jpeg = robot.camera.get_jpeg()
        if jpeg is None:
            raise HTTPException(status_code=503, detail=robot.camera.error or "No camera frame yet")
        return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @api.get("/camera/stream", summary="Live MJPEG video")
    async def camera_stream() -> StreamingResponse:
        if not robot.camera.available:
            raise HTTPException(status_code=503, detail=robot.camera.error or "Camera unavailable")

        async def frames():
            last_id = -1
            while True:
                frame_id, jpeg = robot.camera.get_jpeg()
                if jpeg is not None and frame_id != last_id:
                    last_id = frame_id
                    yield (
                        b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                        + str(len(jpeg)).encode()
                        + b"\r\n\r\n"
                        + jpeg
                        + b"\r\n"
                    )
                await asyncio.sleep(1.0 / robot.camera.fps)

        return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")

    @api.post("/detection", summary="Turn dog detection on or off")
    def detection_set(settings: DetectionSettings) -> Dict[str, Any]:
        robot.detector.enabled = settings.enabled
        return robot.detector.status()

    app.include_router(api)

    # ---- websocket ---------------------------------------------------

    def handle_ws_message(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        kind = msg.get("type")
        if kind == "drive":
            robot.drive(float(msg.get("vx", 0)), float(msg.get("vy", 0)), float(msg.get("omega", 0)))
        elif kind == "stop":
            robot.stop_all()
        elif kind == "feed":
            ok = robot.feed(int(msg.get("portions", 1)), source="manual")
            return {"type": "ack", "action": "feed", "ok": ok}
        elif kind == "launch":
            return {"type": "ack", "action": "launch", "ok": True, **robot.launch(msg.get("power"), msg.get("duration"))}
        elif kind == "launcher_stop":
            robot.launcher.stop()
        elif kind == "ping":
            return {"type": "pong"}
        else:
            return {"type": "error", "message": f"unknown message type: {kind}"}
        return None

    @app.websocket("/ws")
    async def websocket(ws: WebSocket) -> None:
        if token and ws.query_params.get("token") != token:
            await ws.close(code=4401)
            return
        await ws.accept()

        async def push() -> None:
            last_event = robot.events.last_id
            while True:
                await ws.send_json({"type": "status", "data": robot.status()})
                for event in robot.events.list(limit=0, since_id=last_event):
                    last_event = event["id"]
                    await ws.send_json({"type": "event", "data": event})
                await asyncio.sleep(1.0 / STATUS_HZ)

        pusher = asyncio.create_task(push())
        drove = False
        try:
            while True:
                msg = await ws.receive_json()
                try:
                    drove = drove or msg.get("type") == "drive"
                    reply = handle_ws_message(msg)
                except (TypeError, ValueError) as exc:
                    reply = {"type": "error", "message": str(exc)}
                if reply is not None:
                    await ws.send_json(reply)
        except WebSocketDisconnect:
            pass
        except Exception:  # noqa: BLE001
            log.exception("WebSocket error")
        finally:
            pusher.cancel()
            # If the driver's connection drops, do not keep rolling.
            if drove and not robot.navigator.active:
                robot.drivetrain.stop()

    return app
