"""
Petri dishes stage stepper control (direct GPIO STEP + DIR + LIMIT).

Pin mapping (BCM) — driver pins swapped with incubator_lid on this unit:
- DIR  : 17
- STEP : 18
- LIMIT: 6 (PUD_UP, pressed -> LOW)
"""

import time
import RPi.GPIO as GPIO

DIR_PIN = 17
STEP_PIN = 18
LIMIT_PIN = 6

STEP_DELAY = 0.001
# Safety cap — homing normally stops on the limit switch.
HOMING_MAX_STEPS = 5000

# Swap these if the motor runs the wrong way.
UP = GPIO.HIGH
DOWN = GPIO.LOW

_initialized = False


def _ensure_gpio():
    global _initialized
    if _initialized:
        return
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(DIR_PIN, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(STEP_PIN, GPIO.OUT, initial=GPIO.LOW)
    # Direct limit switch on Raspberry Pi GPIO.
    GPIO.setup(LIMIT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    _initialized = True


def _limit_pressed():
    _ensure_gpio()
    return GPIO.input(LIMIT_PIN) == GPIO.LOW


def _step(delay=STEP_DELAY):
    GPIO.output(STEP_PIN, GPIO.HIGH)
    time.sleep(delay)
    GPIO.output(STEP_PIN, GPIO.LOW)
    time.sleep(delay)


def _move(steps, direction, delay=STEP_DELAY, stop_on_limit=False):
    _ensure_gpio()
    GPIO.output(DIR_PIN, direction)
    time.sleep(delay)
    for _ in range(max(0, int(steps))):
        if stop_on_limit and _limit_pressed():
            print("Petri dishes: limit switch pressed -> stopping.")
            break
        _step(delay=delay)


def petri_dishes_up(steps):
    """Move stage away from home by fixed steps."""
    _move(steps, direction=UP, stop_on_limit=False)


def petri_dishes_down(steps):
    """Move stage toward home; stop early if limit switch is pressed."""
    _move(steps, direction=DOWN, stop_on_limit=True)


def petri_dishes_home():
    """Move toward home until limit switch is pressed."""
    _ensure_gpio()
    GPIO.output(DIR_PIN, DOWN)
    time.sleep(STEP_DELAY)
    for _ in range(HOMING_MAX_STEPS):
        if _limit_pressed():
            print("Petri dishes: home reached.")
            return
        _step(delay=STEP_DELAY)
    print("Petri dishes: homing stopped (max steps safety limit reached).")


def cleanup():
    """Release module state (global GPIO cleanup is managed by main app)."""
    global _initialized
    _initialized = False


# Backward-compatible aliases used in some scripts.
Petri_dishes_up = petri_dishes_up
Petri_dishes_down = petri_dishes_down
Petri_dishes_home = petri_dishes_home