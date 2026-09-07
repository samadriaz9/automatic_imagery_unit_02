"""
Camera focus / zoom test.

1. Home the camera motor, then move UP 2000 steps.
2. Pulse camera relay the same way as main.py (GPIO 21, 4 s, active-low).
3. Live OpenCV preview so you can set zoom / focus.
4. Close the window (or press Q): pulse relay 4 s (camera OFF) and GPIO.cleanup().

Run:
    python camera_focus_test.py
"""
import sys
import time

import cv2
import RPi.GPIO as GPIO

from camera_module import Camera_home, Camera_up, cleanup as camera_motor_cleanup

# Same relay wiring as main.py (not GPIO 25).
CAMERA_RELAY_GPIO = 21
CAMERA_RELAY_ACTIVE = GPIO.LOW
CAMERA_RELAY_INACTIVE = GPIO.HIGH
CAMERA_RELAY_PULSE_S = 4.0
CAMERA_UP_STEPS = 2700
CAMERA_BOOT_WAIT_S = 10.0
PREVIEW_WINDOW = "Camera focus / zoom — press Q to close"


def _setup_camera_relay_output():
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(CAMERA_RELAY_GPIO, GPIO.OUT, initial=CAMERA_RELAY_INACTIVE)


def _release_camera_relay_pin():
    try:
        GPIO.setup(CAMERA_RELAY_GPIO, GPIO.IN)
    except Exception:
        pass


def pulse_camera_relay(contact_seconds=CAMERA_RELAY_PULSE_S):
    """Same momentary latch pulse as main.py: LOW 4 s, HIGH, then pin as INPUT."""
    _setup_camera_relay_output()
    GPIO.output(CAMERA_RELAY_GPIO, CAMERA_RELAY_ACTIVE)
    time.sleep(max(0.0, float(contact_seconds)))
    GPIO.output(CAMERA_RELAY_GPIO, CAMERA_RELAY_INACTIVE)
    _release_camera_relay_pin()


def open_usb_camera(device_index=0):
    if sys.platform.startswith("linux"):
        cap = cv2.VideoCapture(int(device_index), cv2.CAP_V4L2)
    else:
        cap = cv2.VideoCapture(int(device_index))
    if not cap.isOpened():
        return None
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    return cap


def show_preview(cap):
    print("Preview open. Adjust zoom / focus, then press Q or close the window.")
    cv2.namedWindow(PREVIEW_WINDOW, cv2.WINDOW_NORMAL)
    while True:
        ok, frame = cap.read()
        if ok:
            cv2.imshow(PREVIEW_WINDOW, frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), ord("Q"), 27):
            break
        try:
            if cv2.getWindowProperty(PREVIEW_WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
        except cv2.error:
            break
    cv2.destroyAllWindows()


def shutdown():
    print(f"Camera OFF: relay pulse {CAMERA_RELAY_PULSE_S:.0f}s on GPIO {CAMERA_RELAY_GPIO}...")
    pulse_camera_relay(CAMERA_RELAY_PULSE_S)
    camera_motor_cleanup()
    GPIO.cleanup()
    print("GPIO released.")


def main():
    cap = None
    try:
        Camera_home()
        Camera_up(CAMERA_UP_STEPS)

        print(f"Camera ON: relay pulse {CAMERA_RELAY_PULSE_S:.0f}s on GPIO {CAMERA_RELAY_GPIO}...")
        pulse_camera_relay(CAMERA_RELAY_PULSE_S)
        print(f"Waiting {CAMERA_BOOT_WAIT_S:.0f}s for USB camera to appear...")
        time.sleep(CAMERA_BOOT_WAIT_S)

        cap = open_usb_camera(0)
        if cap is None:
            print("Could not open USB camera at index 0.")
            return

        show_preview(cap)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()
        shutdown()


if __name__ == "__main__":
    main()
