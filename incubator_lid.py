"""
Incubator lid stepper control (direct GPIO STEP + DIR + LIMIT).

- STEP : GPIO6  (BCM), physical pin 31
- DIR  : GPIO16 (BCM), physical pin 36
- LIMIT: GPIO17 (BCM) — direct switch, PUD_UP, pressed = LOW

Hardware: tie EN on the driver to GND (or per datasheet).
If limit is wired to a different GPIO, change LIMIT_PIN below.
"""
import time

import RPi.GPIO as GPIO

STEP_PIN = 18
DIR_PIN = 17
LIMIT_PIN = 6

STEP_DELAY = 0.001
# Safety cap only — homing normally stops on the limit switch.
HOMING_MAX_STEPS = 10000

UP = GPIO.HIGH
DOWN = GPIO.LOW

_initialized = False


def _ensure_gpio():
    global _initialized
    if _initialized:
        return
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(STEP_PIN, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(DIR_PIN, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(LIMIT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    _initialized = True


def _limit_pressed():
    _ensure_gpio()
    return GPIO.input(LIMIT_PIN) == GPIO.LOW


def _pulse_step(delay=STEP_DELAY):
    GPIO.output(STEP_PIN, GPIO.HIGH)
    time.sleep(delay)
    GPIO.output(STEP_PIN, GPIO.LOW)
    time.sleep(delay)


def _move(steps, direction, delay=STEP_DELAY):
    _ensure_gpio()
    GPIO.output(DIR_PIN, direction)
    time.sleep(delay)
    for _ in range(max(0, int(steps))):
        _pulse_step(delay=delay)


def incubator_lid_up(steps):
    """Move incubator lid UP (open) by the given number of steps."""
    print(f"Incubator lid: moving UP {steps} steps")
    _move(steps, direction=UP)


def incubator_lid_down(steps):
    """Move incubator lid DOWN (close) by the given number of steps."""
    print(f"Incubator lid: moving DOWN {steps} steps")
    _move(steps, direction=DOWN)


def incubator_lid_home():
    """Move UP until the limit switch is pressed (no steps if already at home)."""
    print("Incubator lid: homing UP until limit switch is pressed")
    _ensure_gpio()

    if _limit_pressed():
        print("Incubator lid: limit switch already pressed, homing stop.")
        return

    GPIO.output(DIR_PIN, UP)
    time.sleep(STEP_DELAY)

    for _ in range(HOMING_MAX_STEPS):
        if _limit_pressed():
            print("Incubator lid: limit switch detected, homing stop.")
            return
        _pulse_step()

    print("Incubator lid: homing stopped (max steps safety limit reached).")


# Optional CamelCase aliases
Incubator_lid_up = incubator_lid_up
Incubator_lid_down = incubator_lid_down
Incubator_lid_home = incubator_lid_home


def cleanup():
    """Release state (GPIO cleanup handled by main)."""
    global _initialized
    _initialized = False
