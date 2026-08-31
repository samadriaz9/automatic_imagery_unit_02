import RPi.GPIO as GPIO
import cv2
import time
import os
from datetime import datetime
 
DIR_PIN   = 23
STEP_PIN  = 24
RELAY_PIN = 26
LIMIT_PIN = 5
 
STEP_DELAY     = 0.001
HOME_STEPS     = 2500
STEPS_PER_MOVE = 100
TOTAL_PICS     = 28
 
LEFT  = GPIO.HIGH
RIGHT = GPIO.LOW
 
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(DIR_PIN,   GPIO.OUT)
GPIO.setup(STEP_PIN,  GPIO.OUT)
GPIO.setup(RELAY_PIN, GPIO.OUT)
GPIO.setup(LIMIT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.output(RELAY_PIN, GPIO.HIGH)
 
def step(delay=STEP_DELAY):
    GPIO.output(STEP_PIN, GPIO.HIGH)
    time.sleep(delay)
    GPIO.output(STEP_PIN, GPIO.LOW)
    time.sleep(delay)

def move(steps, direction):
    GPIO.output(DIR_PIN, direction)
    for _ in range(steps):
        step()
 
def relay_toggle():
    # pulse LOW then back to HIGH = one toggle
    GPIO.output(RELAY_PIN, GPIO.LOW)
    time.sleep(0.5)
    GPIO.output(RELAY_PIN, GPIO.HIGH)
    time.sleep(0.5)
 
def home():
    print("Moving to limit switch...")
    GPIO.output(DIR_PIN, LEFT)
    while GPIO.input(LIMIT_PIN) == GPIO.HIGH:
        step()
    print("Limit switch reached. Moving to start position...")
    move(HOME_STEPS, RIGHT)
    print("Ready.")
 
def focus_check():
    # Turn camera ON then relay back to neutral
    relay_toggle()
    print("Camera ON --adjust focus. Press Q when ready.")
    time.sleep(1)
    cap = cv2.VideoCapture(0)
    while True:
        ret, frame = cap.read()
        if ret:
            cv2.imshow("Focus Check - Press Q when ready", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    cap.release()
    cv2.destroyAllWindows()
    print("Focus confirmed!")
 
def capture(cap, folder, index):
    ret, frame = cap.read()
    if ret:
        path = os.path.join(folder, f"pic_{index:02d}.jpg")
        cv2.imwrite(path, frame)
        print(f"  Saved: pic_{index:02d}.jpg")
        return frame
    return None
 
def run():
    home()
    focus_check()
 
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = os.path.join(os.path.expanduser("~"), f"scan_{timestamp}")
    os.makedirs(folder)
    print(f"Saving to: {folder}")
 
    cap = cv2.VideoCapture(0)
    frames = []
    print(f"Scanning {TOTAL_PICS} pictures...")
 
    for i in range(1, TOTAL_PICS + 1):
        print(f"  Picture {i}/{TOTAL_PICS}")
        for _ in range(4):
            move(STEPS_PER_MOVE, RIGHT)
            time.sleep(0.2)
            move(STEPS_PER_MOVE, LEFT)
            time.sleep(0.2)
        time.sleep(0.5)
        frame = capture(cap, folder, i)
        if frame is not None:
            frames.append(frame)
 
    cap.release()
 
    if frames:
        combined = cv2.hconcat(frames)
        cv2.imwrite(os.path.join(folder, "full_combined.jpg"), combined)
        print("Combined image saved.")
 
    print(f"Scan complete! Files saved in: {folder}")
 
# -- MAIN LOOP -------------------------
try:
    while True:
        print("\n1. Run   2. Exit")
        c = input("Choice: ").strip()
        if c == "1":
            run()
        elif c == "2":
            relay_toggle()  # camera OFF
            print("Camera OFF. Goodbye!")
            break
 
except KeyboardInterrupt:
    print("\nStopped.")
    relay_toggle()  # camera OFF
    print("Camera OFF.")
 
finally:
    GPIO.cleanup()
