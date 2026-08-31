"""
Main script for Filteration Flask, Filteration Unit and Suction Pump control.
Runs homing (down until limit switch via PCF8574) and then movements.

Filteration flask: STEP=18, DIR=23 (BCM); EN tied on hardware (see filteration_flask.py).
Filteration unit: STEP=13, DIR=19 (BCM); EN tied on hardware (see filteration_unit.py).
Suction pump lift (stepper): STEP=21, DIR=12 (BCM); EN tied on hardware (see suction_pump_up_down.py). Flask/upper DC pump: GPIO 11 RPWM (see upper_suction_pump.py); leave GPIO 4 for DS18B20.
Petri dishes: STEP=10, DIR=22 (BCM); EN tied on hardware (see petri_dishes.py).
Media dispensor: STEP=24, DIR=27 (BCM); physical pins 18 & 13 (see Media_dispensor.py).
Suction pipe: STEP=8, DIR=20 (BCM); no limit switch — use up/down with steps only (see suction_pipe.py).
Incubator lid: STEP=6, DIR=16, LIMIT=17 (BCM); physical pins 31, 36 & 11 (see incubator_lid.py).
Incubation heaters: lower BTS GPIO 12 (pin 32), upper BTS GPIO 26 (pin 37, +30% duty); see incubation_module.py.
Filtration solenoid: was GPIO 26 — confirm wiring if solenoid and lower heater share hardware.

Shutdown: Ctrl+C runs full cleanup (see shutdown_all). SIGTERM (kill) also cleans up.
"""
import atexit
import contextlib
import gc
import io
import signal
import sys
import time
import cv2

def _missing_function(module_name, func_name):
    def _inner(*_args, **_kwargs):
        raise RuntimeError(f"Missing module '{module_name}': cannot run '{func_name}()'")
    return _inner


def _missing_cleanup(*_args, **_kwargs):
    return None


try:
    from suction_pump_up_down import (
        suction_pump_up,
        suction_pump_down,
        suction_pump_home,
        cleanup as suction_lift_cleanup,
    )
except ModuleNotFoundError:
    suction_pump_up = _missing_function("suction_pump_up_down", "suction_pump_up")
    suction_pump_down = _missing_function("suction_pump_up_down", "suction_pump_down")
    suction_pump_home = _missing_function("suction_pump_up_down", "suction_pump_home")
    suction_lift_cleanup = _missing_cleanup

try:
    from filteration_flask import (
        Filteration_flask_up,
        Filteration_flask_down,
        filteration_flask_config,
        cleanup as filteration_cleanup,
    )
except ModuleNotFoundError:
    Filteration_flask_up = _missing_function("filteration_flask", "Filteration_flask_up")
    Filteration_flask_down = _missing_function("filteration_flask", "Filteration_flask_down")
    filteration_flask_config = _missing_function("filteration_flask", "filteration_flask_config")
    filteration_cleanup = _missing_cleanup

try:
    from filteration_unit import (
        Filteration_unit_up,
        Filteration_unit_down,
        filteration_unit_config,
        cleanup as filteration_unit_cleanup,
    )
except ModuleNotFoundError:
    Filteration_unit_up = _missing_function("filteration_unit", "Filteration_unit_up")
    Filteration_unit_down = _missing_function("filteration_unit", "Filteration_unit_down")
    filteration_unit_config = _missing_function("filteration_unit", "filteration_unit_config")
    filteration_unit_cleanup = _missing_cleanup

try:
    from upper_suction_pump import (
        upper_suction_pump_on,
        upper_suction_pump_off,
        cleanup as suction_cleanup,
    )
except ModuleNotFoundError:
    upper_suction_pump_on = _missing_function("upper_suction_pump", "upper_suction_pump_on")
    upper_suction_pump_off = _missing_function("upper_suction_pump", "upper_suction_pump_off")
    suction_cleanup = _missing_cleanup

try:
    from consumable import cleanup as consumable_cleanup
except ModuleNotFoundError:
    consumable_cleanup = _missing_cleanup

from device_config import MAX_PETRI_DISHES
from workflow_steps import (
    capture_petri_dishes,
    run_timed_picture_study,
    step_01_all_home,
    step_02_insert_petri_dishes,
    step_03_shift_for_incubation,
    step_04_incubation,
    step_05_post_imaging_cleanup,
    step_05_prepare_imaging,
    step_06_sterilize,
)


def _ask_num_petri_dishes():
    """Ask how many petri dishes to image (1 = single dish, same as before)."""
    default = 1
    raw = input(f"How many petri dishes to image (1-{MAX_PETRI_DISHES})? [{default}]: ").strip()
    if not raw:
        return default
    try:
        n = int(raw)
    except ValueError:
        print(f"Invalid number, using {default}.")
        return default
    if n < 1 or n > MAX_PETRI_DISHES:
        print(f"Using clamped value (1-{MAX_PETRI_DISHES}).")
        return max(1, min(MAX_PETRI_DISHES, n))
    return n

try:
    from filteration_suction_pump import (
        filteration_suction_pump_on,
        filteration_suction_pump_off,
        cleanup as filteration_suction_cleanup,
    )
except ModuleNotFoundError:
    filteration_suction_pump_on = _missing_function("filteration_suction_pump", "filteration_suction_pump_on")
    filteration_suction_pump_off = _missing_function("filteration_suction_pump", "filteration_suction_pump_off")
    filteration_suction_cleanup = _missing_cleanup

from petri_dishes import (
    petri_dishes_home,
    petri_dishes_up,
    petri_dishes_down,
    cleanup as petri_dishes_cleanup,
)
from camera_module import (
    Camera_home,
    Camera_up,
    Camera_down,
    cleanup as camera_cleanup,
)

try:
    from media_dispensor import (
        Media_dispensor_home,
        Media_dispensor_up,
        Media_dispensor_down,
        cleanup as media_dispensor_cleanup,
    )
except ModuleNotFoundError:
    Media_dispensor_home = _missing_function("media_dispensor", "Media_dispensor_home")
    Media_dispensor_up = _missing_function("media_dispensor", "Media_dispensor_up")
    Media_dispensor_down = _missing_function("media_dispensor", "Media_dispensor_down")
    media_dispensor_cleanup = _missing_cleanup

try:
    from suction_pipe import (
        suction_pipe_home,
        suction_pipe_up,
        suction_pipe_down,
        cleanup as suction_pipe_cleanup,
    )
except ModuleNotFoundError:
    suction_pipe_home = _missing_function("suction_pipe", "suction_pipe_home")
    suction_pipe_up = _missing_function("suction_pipe", "suction_pipe_up")
    suction_pipe_down = _missing_function("suction_pipe", "suction_pipe_down")
    suction_pipe_cleanup = _missing_cleanup

from incubator_lid import (
    incubator_lid_home,
    incubator_lid_up,
    incubator_lid_down,
    cleanup as incubator_lid_cleanup,
)

try:
    from usb_camera_thread import stop_usb_camera_thread
except ModuleNotFoundError:
    def stop_usb_camera_thread(_worker):
        return None

try:
    from solinoid_value_to_filteration import (
        solinoid_value_to_filteration,
        water_level_reached,
        cleanup as solenoid_cleanup,
    )
except ModuleNotFoundError:
    solinoid_value_to_filteration = _missing_function("solinoid_value_to_filteration", "solinoid_value_to_filteration")
    water_level_reached = _missing_function("solinoid_value_to_filteration", "water_level_reached")
    solenoid_cleanup = _missing_cleanup

try:
    from solinoid_value_drain import cleanup as drain_solenoid_cleanup
except ModuleNotFoundError:
    drain_solenoid_cleanup = _missing_cleanup

try:
    from solinoid_waste import cleanup as waste_solenoid_cleanup
except ModuleNotFoundError:
    waste_solenoid_cleanup = _missing_cleanup
import RPi.GPIO as GPIO

# Camera relay control (direct GPIO, no smbus/PCF8574).
# Your wiring: physical pin 22 -> BCM25, active-low (relay OFF = HIGH).
CAMERA_RELAY_GPIO = 25
CAMERA_RELAY_ACTIVE = GPIO.LOW
CAMERA_RELAY_INACTIVE = GPIO.HIGH
CAMERA_RELAY_PULSE_S = 4.0
CAMERA_BOOT_WAIT_S = 10.0
CAMERA_POWER_ON_ATTEMPTS = 3
CAMERA_BOOT_POST_CHECKS = 6
CAMERA_BOOT_CHECK_INTERVAL_S = 2.0
CAMERA_POWER_CYCLE_SETTLE_S = 2.0


def _setup_camera_relay_output():
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(CAMERA_RELAY_GPIO, GPIO.OUT, initial=CAMERA_RELAY_INACTIVE)


def _release_camera_relay_pin():
    """Stop driving the relay line (relay board / latch holds camera state)."""
    try:
        GPIO.setup(CAMERA_RELAY_GPIO, GPIO.IN)
    except Exception:
        pass


def pulse_camera_relay(contact_seconds=CAMERA_RELAY_PULSE_S):
    """
    Momentary relay contact then release GPIO (toggle / latch wiring).

    Active-low: LOW for contact_seconds, return to HIGH, then set pin INPUT so
    the coil is not held energized. Same pulse toggles camera ON or OFF.
    """
    _setup_camera_relay_output()
    GPIO.output(CAMERA_RELAY_GPIO, CAMERA_RELAY_ACTIVE)
    time.sleep(max(0.0, float(contact_seconds)))
    GPIO.output(CAMERA_RELAY_GPIO, CAMERA_RELAY_INACTIVE)
    _release_camera_relay_pin()


def power_off_usb_camera():
    """Toggle camera OFF (4 s relay pulse, pin released)."""
    print(f"[Camera] Relay OFF pulse ({CAMERA_RELAY_PULSE_S:.0f}s), pin released...")
    pulse_camera_relay(CAMERA_RELAY_PULSE_S)


def _suppress_opencv_logs():
    try:
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
    except Exception:
        pass


def _usb_camera_probe(device_index=0, read_tries=3, wait_s=0.15):
    """
    Probe USB camera once.

    Returns:
        'ready'        – opened and delivered a frame
        'open_failed'  – V4L2 cannot open /dev/videoN (can't open camera by index)
        'read_failed'  – opened but no valid frame yet
    """
    _suppress_opencv_logs()
    idx = int(device_index)
    last = "open_failed"
    for _ in range(max(1, int(read_tries))):
        cap = _open_usb_camera(device_index=idx)
        if cap is None:
            last = "open_failed"
            time.sleep(float(wait_s))
            continue
        try:
            if sys.platform.startswith("linux"):
                with contextlib.redirect_stderr(io.StringIO()):
                    ok, frame = cap.read()
            else:
                ok, frame = cap.read()
            if ok and frame is not None:
                return "ready"
            last = "read_failed"
        finally:
            try:
                cap.release()
            except Exception:
                pass
        time.sleep(float(wait_s))
    return last


def _poll_usb_camera(device_index=0, label="Readiness"):
    """
    Try opening the camera several times (no relay).

    Returns True when a frame is received. On V4L2 open failure, returns False
    immediately so the caller can run a relay power cycle.
    """
    checks = max(1, int(CAMERA_BOOT_POST_CHECKS))
    interval = max(0.0, float(CAMERA_BOOT_CHECK_INTERVAL_S))
    idx = int(device_index)
    for n in range(1, checks + 1):
        print(f"[Camera] {label} check {n}/{checks} (/dev/video{idx})...")
        status = _usb_camera_probe(device_index=idx, read_tries=2, wait_s=0.1)
        if status == "ready":
            return True
        if status == "open_failed":
            print(
                f"[Camera] V4L2: can't open camera by index (/dev/video{idx})"
            )
            return False
        print("[Camera] Device opened but no frame yet, retrying...")
        if n < checks:
            time.sleep(interval)
    return False


def _camera_already_usable(device_index=0):
    """True if the USB camera works now — avoids toggle relay when already on."""
    print("[Camera] Checking if camera is already on (no relay toggle)...")
    if _poll_usb_camera(device_index=device_index, label="Direct"):
        print("[Camera] Camera already on — proceeding to capture")
        return True
    return False


def _check_camera_after_boot(device_index=0):
    """After relay ON + boot wait, poll until the camera streams."""
    return _poll_usb_camera(device_index=device_index, label="Post-boot")


def restart_usb_camera_power(device_index=0):
    """Relay OFF, brief pause, relay ON, boot wait (used after V4L2 open errors)."""
    print("[Camera] Restarting camera power...")
    power_off_usb_camera()
    time.sleep(CAMERA_POWER_CYCLE_SETTLE_S)
    return _power_cycle_camera_on(device_index=device_index)


def _power_cycle_camera_on(device_index=0):
    """Relay ON pulse, wait for USB boot, then poll readiness."""
    print(f"[Camera] Relay ON pulse ({CAMERA_RELAY_PULSE_S:.0f}s), pin released...")
    pulse_camera_relay(CAMERA_RELAY_PULSE_S)
    print(f"[Camera] Waiting {CAMERA_BOOT_WAIT_S:.0f}s for USB boot...")
    time.sleep(CAMERA_BOOT_WAIT_S)
    return _check_camera_after_boot(device_index=device_index)


def ensure_usb_camera_ready(device_index=0, max_attempts=CAMERA_POWER_ON_ATTEMPTS):
    """
    Ensure USB camera is ready for capture.

    Returns:
        (ready, relay_power_was_used)
        relay_power_was_used is True only if a relay pulse was used to turn power on;
        then the caller should pulse relay off after imaging. If the camera was
        already on, no relay is toggled (avoids confusing ON/OFF on toggle wiring).
    """
    if _camera_already_usable(device_index=device_index):
        return True, False

    print("[Camera] Camera not available yet — trying relay power cycle...")
    attempts = max(1, int(max_attempts))
    for attempt in range(1, attempts + 1):
        print(f"[Camera] Power-on attempt {attempt}/{attempts}")
        if attempt == 1:
            ok = _power_cycle_camera_on(device_index=device_index)
        else:
            print(
                "[Camera] Will restart camera power (relay OFF, then ON) "
                "after open failure"
            )
            ok = restart_usb_camera_power(device_index=device_index)
        if ok:
            print("[Camera] USB camera ready")
            return True, True
        print(f"[Camera] Not ready after attempt {attempt}/{attempts}")
    return False, False


def return_all_home_positions(pulse_camera_off=False):
    """Homing recovery when the USB camera cannot be opened after all retries."""
    print("[Recovery] Returning all modules to home positions...")
    if pulse_camera_off:
        try:
            power_off_usb_camera()
        except Exception as exc:
            print(f"[Recovery] Camera power-off warning: {exc}")
    Camera_home()
    incubator_lid_home()
    petri_dishes_home()
    print("[Recovery] All modules homed.")

# --- Run once: stops PWM/relays/solenoid and releases GPIO (helps avoid drivers heating when idle) ---
_shutdown_done = False
_usb_camera_worker = None


def _open_usb_camera(device_index=0):
    """Open USB camera with Linux V4L2 backend to avoid GStreamer instability."""
    _suppress_opencv_logs()
    idx = int(device_index)
    if sys.platform.startswith("linux"):
        with contextlib.redirect_stderr(io.StringIO()):
            cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
    else:
        cap = cv2.VideoCapture(idx)
    if not cap.isOpened():
        return None
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    return cap


def shutdown_all():
    """Idempotent full cleanup. Call on exit, Ctrl+C, or SIGTERM."""
    global _shutdown_done
    if _shutdown_done:
        return
    _shutdown_done = True
    print("\n[Shutdown] Releasing GPIO and stopping outputs...")

    try:
        from incubation_module import release_incubation_heaters

        release_incubation_heaters()
    except Exception as e:
        print(f"  Cleanup warning (incubation heaters): {e}")

    # Stop DC/PWM and relays first; then stepper modules; solenoid off; GPIO.cleanup last.
    for name, fn in (
        ("filteration_suction_pump", filteration_suction_cleanup),
    ("upper_suction_pump (DC)", suction_cleanup),
        ("suction_pump_up_down", suction_lift_cleanup),
        ("solenoid", solenoid_cleanup),
        ("drain_solenoid", drain_solenoid_cleanup),
        ("waste_solenoid", waste_solenoid_cleanup),
        ("consumable", consumable_cleanup),
        ("filteration_flask", filteration_cleanup),
        ("filteration_unit", filteration_unit_cleanup),
        ("petri_dishes", petri_dishes_cleanup),
        ("camera", camera_cleanup),
        ("media_dispensor", media_dispensor_cleanup),
        ("suction_pipe", suction_pipe_cleanup),
        ("incubator_lid", incubator_lid_cleanup),
    ):
        try:
            fn()
        except Exception as e:
            print(f"  Cleanup warning ({name}): {e}")

    # Finalize PWM wrappers while GPIO is still valid (avoids RPi.GPIO PWM.__del__ after cleanup).
    gc.collect()

    try:
        GPIO.cleanup()
    except Exception:
        pass
    print("[Shutdown] Done.")


def _on_sigterm(signum, frame):
    shutdown_all()
    sys.exit(0)


# kill / systemd stop without -9 This is the kill signal handler
signal.signal(signal.SIGTERM, _on_sigterm)
atexit.register(shutdown_all)


def run_workflow():
    input("Step 01: All Home — press Enter")
    step_01_all_home()

    input("Step 02: Insert petri dishes — press Enter")
    step_02_insert_petri_dishes()

    input("Step 03: Shift for incubation — press Enter")
    step_03_shift_for_incubation()

    input("Step 04: Start incubation — press Enter")
    step_04_incubation()

    input("Step 05: Take pictures — press Enter")
    num_petri = _ask_num_petri_dishes()
    step_05_prepare_imaging()
    try:
        exp_dir = capture_petri_dishes(num_petri)
        print(f"Imaging completed — saved under: {exp_dir}")
    except Exception as e:
        print(f"Imaging failed: {e}")
    step_05_post_imaging_cleanup()

    input("Step 06: Sterilize — press Enter")
    step_06_sterilize()


if __name__ == "__main__":
    try:
        run_workflow()
    except KeyboardInterrupt:
        print("\nInterrupted (Ctrl+C).")
    finally:
        stop_usb_camera_thread(_usb_camera_worker)
        shutdown_all()
