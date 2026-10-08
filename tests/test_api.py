import time

import pytest
from fastapi.testclient import TestClient

from paws.robot import Robot
from paws.server import create_app
from tests.conftest import make_config


@pytest.fixture
def client():
    robot = Robot(make_config(), persist=False)
    with TestClient(create_app(robot)) as c:
        c.robot = robot
        yield c


def test_status_reports_simulation(client):
    s = client.get("/api/status").json()
    assert s["simulated"] is True
    assert s["mode"] == "manual"
    assert set(s["pose"]) >= {"x", "y", "theta"}


def test_drive_then_watchdog(client):
    assert client.post("/api/drive", json={"vx": 0.5}).status_code == 200
    assert client.get("/api/status").json()["drive"]["vx"] == pytest.approx(0.5)
    time.sleep(0.8)
    s = client.get("/api/status").json()
    assert s["drive"]["vx"] == 0
    assert s["pose"]["x"] > 0.05  # it moved while the command was live


def test_drive_rejects_out_of_range(client):
    assert client.post("/api/drive", json={"vx": 3}).status_code == 422


def test_feed_and_busy(client):
    client.robot.feeder.open_time = 0.3
    assert client.post("/api/feeder/dispense", json={"portions": 1}).json()["portions"] == 1
    assert client.post("/api/feeder/dispense", json={"portions": 1}).status_code == 409


def test_launch_and_stop(client):
    r = client.post("/api/launcher/launch", json={"power": 0.5, "duration": 2}).json()
    assert r["power"] == 0.5
    assert client.get("/api/status").json()["launcher"]["running"] is True
    client.post("/api/stop")
    assert client.get("/api/status").json()["launcher"]["running"] is False


def test_schedule_crud(client):
    created = client.post("/api/schedule", json={"time": "07:30", "portions": 2, "days": [0, 2, 4]})
    assert created.status_code == 201
    entry = created.json()
    listing = client.get("/api/schedule").json()
    assert [e["id"] for e in listing["entries"]] == [entry["id"]]
    assert listing["next"] is not None
    patched = client.patch(f"/api/schedule/{entry['id']}", json={"enabled": False}).json()
    assert patched["enabled"] is False and patched["time"] == "07:30"
    assert client.post("/api/schedule", json={"time": "25:00"}).status_code == 422
    assert client.delete(f"/api/schedule/{entry['id']}").status_code == 200
    assert client.delete(f"/api/schedule/{entry['id']}").status_code == 404


def test_goto_runs_in_background_loop(client):
    client.post("/api/nav/goto", json={"x": 0.2, "y": 0.1})
    assert client.get("/api/status").json()["mode"] == "auto"
    deadline = time.time() + 8
    while time.time() < deadline and client.get("/api/status").json()["navigation"]["active"]:
        time.sleep(0.1)
    s = client.get("/api/status").json()
    assert s["navigation"]["state"] == "reached"
    assert s["pose"]["x"] == pytest.approx(0.2, abs=0.06)
    assert s["pose"]["y"] == pytest.approx(0.1, abs=0.06)


def test_camera_snapshot_and_stream(client):
    deadline = time.time() + 3
    while time.time() < deadline:
        r = client.get("/api/camera/snapshot")
        if r.status_code == 200:
            break
        time.sleep(0.1)
    assert r.headers["content-type"] == "image/jpeg"
    assert r.content[:2] == b"\xff\xd8"


def test_events_and_since(client):
    client.post("/api/feeder/dispense", json={"portions": 1})
    events = client.get("/api/events").json()["events"]
    assert events[-1]["type"] == "feed"
    newer = client.get(f"/api/events?since={events[-1]['id']}").json()["events"]
    assert newer == []


def test_websocket_drive_and_status(client):
    with client.websocket_connect("/ws") as ws:
        first = ws.receive_json()
        assert first["type"] == "status"
        ws.send_json({"type": "drive", "vx": 0, "vy": 0.4, "omega": 0})
        ws.send_json({"type": "ping"})
        seen = []
        while "pong" not in seen:
            seen.append(ws.receive_json()["type"])
        assert client.robot.drivetrain.applied[1] == pytest.approx(0.4)
        ws.send_json({"type": "feed", "portions": 1})
        kinds = {}
        deadline = time.time() + 3
        while time.time() < deadline and not {"ack", "event"} <= set(kinds):
            msg = ws.receive_json()
            kinds[msg["type"]] = msg
        assert kinds["ack"]["ok"] is True
        assert kinds["event"]["data"]["type"] == "feed"
    time.sleep(0.1)
    assert not client.robot.drivetrain.moving  # stopped on disconnect


def test_token_is_enforced():
    robot = Robot(make_config(server={"token": "secret"}), persist=False)
    with TestClient(create_app(robot)) as c:
        assert c.get("/api/status").status_code == 401
        assert c.get("/api/status", headers={"X-PAWS-Token": "secret"}).status_code == 200
        assert c.get("/api/status?token=secret").status_code == 200
