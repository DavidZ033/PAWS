import pytest

from paws.drivetrain import mix


def test_forward_drives_all_wheels_forward():
    powers, scale = mix(1, 0, 0)
    assert powers == (1, 1, 1, 1)
    assert scale == 1


def test_strafe_left_uses_diagonal_pairs():
    fl, fr, bl, br = mix(0, 1, 0)[0]
    assert (fl, fr, bl, br) == (-1, 1, 1, -1)


def test_turn_counter_clockwise():
    fl, fr, bl, br = mix(0, 0, 1)[0]
    assert (fl, bl) == (-1, -1)
    assert (fr, br) == (1, 1)


def test_powers_are_scaled_not_clipped():
    powers, scale = mix(1, 1, 1)
    assert max(abs(p) for p in powers) == pytest.approx(1.0)
    assert scale == pytest.approx(1 / 3)
    # Ratios between wheels are preserved.
    assert powers[1] == pytest.approx(1.0)
    assert powers[0] == pytest.approx(-1 / 3)


def test_motor_pins_follow_power(robot):
    motor = robot.drivetrain.motors["front_left"]
    motor.set(0.5)
    assert (motor._in1.value, motor._in2.value) == (1, 0)
    assert motor._pwm.value == pytest.approx(0.5)
    motor.set(-0.25)
    assert (motor._in1.value, motor._in2.value) == (0, 1)
    assert motor._pwm.value == pytest.approx(0.25)
    motor.stop()
    assert (motor._in1.value, motor._in2.value, motor._pwm.value) == (0, 0, 0)


def test_inverted_motor_swaps_direction(robot):
    right = robot.launcher.motors[1]
    assert right.inverted
    right.set(1.0)
    assert (right._in1.value, right._in2.value) == (0, 1)
