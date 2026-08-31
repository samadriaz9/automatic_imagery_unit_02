import RPi.GPIO as GPIO
import time

# Camera motor pins (BCM numbering)

DIR_PIN   = 23
STEP_PIN  = 24
LIMIT_PIN = 5

delay = 0.001   # speed control

# One-time GPIO setup
_initialized = False


def _ensure_gpio():
    """Initialize GPIO for camera motor (once)."""
    global _initialized
    if not _initialized:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(STEP_PIN, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(DIR_PIN, GPIO.OUT, initial=GPIO.LOW)
        # Direct limit switch on Raspberry Pi GPIO.
        # Wiring expectation: not pressed=HIGH, pressed=LOW.
        GPIO.setup(LIMIT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        _initialized = True


def _limit_pressed():
    """Return True when direct limit switch is pressed."""
    _ensure_gpio()
    return GPIO.input(LIMIT_PIN) == GPIO.LOW


def _step(steps, direction_high):
    """Run a given number of steps in one direction."""
    _ensure_gpio()
    GPIO.output(DIR_PIN, GPIO.HIGH if direction_high else GPIO.LOW)

    for _ in range(steps):
        GPIO.output(STEP_PIN, GPIO.HIGH)
        time.sleep(delay)
        GPIO.output(STEP_PIN, GPIO.LOW)
        time.sleep(delay)


def Camera_up(steps):
    """Move camera motor UP by the given number of steps."""
    print(f"Camera: moving UP {steps} steps")
    _step(steps, direction_high=False)  # DIR LOW = UP


def Camera_down(steps):
    """Move camera motor DOWN by the given number of steps."""
    print(f"Camera: moving DOWN {steps} steps")
    _step(steps, direction_high=True)  # DIR HIGH = DOWN


def Camera_home():
    """
    Drive the camera motor DOWN until direct GPIO limit switch is pressed.
    Assumes switch is HIGH normally and LOW when pressed.
    """
    print("Camera: homing DOWN until direct GPIO limit switch is pressed")

    _ensure_gpio()

    # Set direction for DOWN (match Camera_down mapping).
    GPIO.output(DIR_PIN, GPIO.HIGH)

    while True:
        if _limit_pressed():
            print("Camera: limit switch detected, stopping.")
            break

        GPIO.output(STEP_PIN, GPIO.LOW)
        time.sleep(delay)
        GPIO.output(STEP_PIN, GPIO.HIGH)
        time.sleep(delay)


def cleanup():
    """Release module state (GPIO cleanup handled by app shutdown)."""
    global _initialized
    _initialized = False