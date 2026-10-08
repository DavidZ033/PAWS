# Wiring

All pin numbers are **BCM (GPIO) numbers**, not physical header positions. Use <https://pinout.xyz> to translate.

> The pins below are the defaults in `config.yaml`. They are placeholders chosen so that nothing clashes. Rewire the table to match your robot, or change `config.yaml` to match your wiring.

## Motor controllers

Each motor controller channel needs three signals from the Pi:

| Signal | Meaning |
| --- | --- |
| IN1, IN2 | Direction. `1,0` = forward, `0,1` = reverse, `0,0` = coast, `1,1` = brake |
| PWM | Speed, as a duty cycle from 0% to 100% |

| Motor | IN1 | IN2 | PWM |
| --- | --- | --- | --- |
| Drive front left | GPIO 17 | GPIO 27 | GPIO 22 |
| Drive front right | GPIO 23 | GPIO 24 | GPIO 25 |
| Drive back left | GPIO 5 | GPIO 6 | GPIO 13 |
| Drive back right | GPIO 16 | GPIO 20 | GPIO 21 |
| Launcher left | GPIO 7 | GPIO 8 | GPIO 12 |
| Launcher right | GPIO 14 | GPIO 15 | GPIO 18 |

Notes:

* **Share a ground.** The Pi's ground must be connected to the motor controllers' logic ground, or the signals mean nothing.
* **Never power motors from the Pi.** Motor power comes from the battery through the controllers. The Pi only sends 3.3 V logic signals.
* GPIO 14 and 15 are the Pi's serial port. If you use them for a motor, turn off the serial console first: `sudo raspi-config`, Interface Options, Serial Port, "No" to the login shell.
* "Forward" for a drive motor means the direction that pushes the robot forward. Run `python -m paws hwtest` and flip `inverted` in `config.yaml` for any wheel that goes the wrong way. This is easier than swapping wires.
* The two launcher flywheels must spin in opposite directions, which is why one of them is `inverted: true` by default.

## Wheel positions

Looking down at the robot, with the front at the top:

```
            front
        FL /     \ FR
          |  PAWS |
        BL \     / BR
```

Each wheel is turned 45 degrees so its axle points at the centre of the robot.

## Encoders

Two free-spinning omni wheels under the chassis, each with a quadrature encoder (two signal wires, A and B).

| Encoder | A | B | Measures |
| --- | --- | --- | --- |
| enc1 | GPIO 10 | GPIO 9 | Forward and backward travel |
| enc2 | GPIO 11 | GPIO 4 | Sideways travel |

* Power the encoders from **3.3 V**, not 5 V, unless you add level shifters. A 5 V signal can damage a Pi input.
* Pushing the robot forward should make x go up. Pushing it to the left should make y go up. If either goes down instead, set `inverted: true` for that encoder.
* If your two tracking wheels both roll forward (one on each side) instead of one forward and one sideways, set `odometry.layout: parallel` and measure the distance between them into `odometry.track_width`.
* If a tracking wheel is not on the robot's centre line, put its offset in `odometry.enc1_offset` or `odometry.enc2_offset` so spinning on the spot is not mistaken for travel.

## Feeder servo

| Signal | Pin |
| --- | --- |
| Servo signal | GPIO 19 |

* Power the servo from a 5 to 6 V supply that can deliver a couple of amps, not from the Pi's 5 V pin. Connect the grounds together.
* A REV Smart Robot Servo uses pulses from 0.5 ms to 2.5 ms, which is what `min_pulse_ms` and `max_pulse_ms` default to.
* Tune `closed_position` and `open_position` (each from -1 to 1) until the gate fully closes and opens.
* If the servo was programmed for continuous rotation, set `feeder.mode: continuous`.

## Camera

Plug the Pi camera ribbon cable into the CSI connector. Check it with:

```bash
rpicam-hello --list-cameras
```

A USB webcam also works: set `camera.backend: opencv`.

## Free pins

GPIO 2 and 3 (I2C) and GPIO 26 are left free. I2C is the natural place to add a gyro later.
