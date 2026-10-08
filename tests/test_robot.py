import math

import pytest

from paws.robot import Robot
from tests.conftest import make_config

DT = 0.02


def run(robot, seconds, command=None):
    """Step the simulated robot. ``command`` is re-sent every tick if given."""
    t = 1000.0
    for _ in range(int(seconds / DT)):
        if command:
            robot.drive(*command)
            robot._last_drive_cmd = t
        t += DT
        robot.step(DT, now=t)
    return t


def test_odometry_tracks_forward_motion(robot):
    run(robot, 1.0, (0.5, 0, 0))
    pose = robot.odometry.pose
    assert pose.x == pytest.approx(0.5 * 0.8 * 1.0, abs=0.02)
    assert abs(pose.y) < 0.01


def test_odometry_matches_truth_while_strafing_and_turning(robot):
    run(robot, 2.0, (0.3, 0.4, 0.2))
    pose, truth = robot.odometry.pose, robot.sim.true_pose
    assert pose.x == pytest.approx(truth.x, abs=0.01)
    assert pose.y == pytest.approx(truth.y, abs=0.01)
    assert pose.theta == pytest.approx(truth.theta, abs=0.01)
    assert abs(truth.theta) > 0.5  # it really did turn


def test_odometry_with_offset_tracking_wheels():
    r = Robot(make_config(odometry={"enc1_offset": 0.07, "enc2_offset": -0.05}), persist=False)
    try:
        run(r, 2.0, (0.2, -0.3, 0.5))
        pose, truth = r.odometry.pose, r.sim.true_pose
        assert pose.x == pytest.approx(truth.x, abs=0.01)
        assert pose.y == pytest.approx(truth.y, abs=0.01)
    finally:
        r.shutdown()


def test_parallel_layout_measures_heading_from_encoders():
    r = Robot(make_config(odometry={"layout": "parallel", "track_width": 0.25}), persist=False)
    try:
        run(r, 1.5, (0.4, 0, 0.3))
        pose, truth = r.odometry.pose, r.sim.true_pose
        assert pose.theta == pytest.approx(truth.theta, abs=0.01)
        assert pose.x == pytest.approx(truth.x, abs=0.01)
        assert pose.y == pytest.approx(truth.y, abs=0.01)
    finally:
        r.shutdown()


def test_watchdog_stops_stale_drive_command(robot):
    robot.drive(1, 0, 0)
    robot._last_drive_cmd = 1000.0
    robot.step(DT, now=1000.1)
    assert robot.drivetrain.moving
    robot.step(DT, now=1000.0 + robot.watchdog_timeout + 0.1)
    assert not robot.drivetrain.moving


def test_goto_reaches_target(robot):
    robot.goto(1.0, -0.5, math.pi / 2)
    run(robot, 15.0)
    pose = robot.odometry.pose
    assert robot.navigator.state == "reached"
    assert math.hypot(pose.x - 1.0, pose.y + 0.5) < 0.06
    assert pose.theta == pytest.approx(math.pi / 2, abs=0.11)
    assert not robot.drivetrain.moving
    assert robot.events.list(kind="navigation")[-1]["message"] == "Navigation reached"


def test_patrol_visits_every_waypoint_and_loops(robot):
    robot.patrol([{"x": 0.5, "y": 0}, {"x": 0.5, "y": 0.5}, {"x": 0, "y": 0}], loops=2)
    run(robot, 40.0)
    pose = robot.odometry.pose
    assert robot.navigator.state == "reached"
    assert math.hypot(pose.x, pose.y) < 0.06


def test_manual_drive_cancels_navigation_and_keeps_driving(robot):
    robot.goto(5, 5)
    run(robot, 0.5)
    assert robot.navigator.active
    t = run(robot, 0.1, (0, 0.5, 0))
    assert robot.navigator.state == "cancelled"
    assert robot.drivetrain.applied == pytest.approx((0, 0.5, 0))
    # ...and the watchdog still applies afterwards.
    robot.step(DT, now=t + 1.0)
    assert not robot.drivetrain.moving


def test_navigation_times_out(robot):
    robot.navigator.timeout = 1.0
    robot.goto(50, 0)
    run(robot, 2.0)
    assert robot.navigator.state == "timeout"
    assert not robot.drivetrain.moving


def test_stop_all_halts_everything(robot):
    robot.goto(3, 0)
    robot.launch(0.5, 5)
    run(robot, 0.2)
    robot.stop_all()
    assert not robot.drivetrain.moving
    assert not robot.launcher.running
    assert not robot.navigator.active


def test_launcher_spins_then_stops_itself(robot):
    import time

    result = robot.launch(power=0.6, duration=0.15)
    assert result == {"power": 0.6, "duration": 0.15}
    assert robot.launcher.running
    assert all(abs(m.power) == pytest.approx(0.6) for m in robot.launcher.motors)
    time.sleep(0.4)
    assert not robot.launcher.running


def test_launcher_duration_is_capped(robot):
    assert robot.launch(duration=999)["duration"] == robot.launcher.max_run_time
    robot.launcher.stop()


def test_feeder_cycles_servo_and_refuses_overlap(robot):
    positions = []
    original = robot.feeder.servo.set
    robot.feeder.servo.set = lambda v: (positions.append(v), original(v))
    assert robot.feed(2) is True
    assert robot.feed(1) is False  # still busy
    robot.feeder._thread.join()
    assert positions == [0.0, -1.0, 0.0, -1.0]
    assert robot.feeder.total_portions == 2
    assert robot.feeder.servo.value is None  # detached when idle
    kinds = [e["type"] for e in robot.events.list()]
    assert kinds == ["feed", "feed_skipped"]


def test_feeder_caps_portions(robot):
    assert robot.feeder.clamp_portions(99) == robot.feeder.max_portions
