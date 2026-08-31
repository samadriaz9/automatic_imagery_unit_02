import RPi.GPIO as GPIO
import time
 
# -- PINS (BCM numbering) ---------------
DIR_PIN   = 27   # CW+
STEP_PIN  = 22   # CLK+
LIMIT_PIN = 13
 
# -- DIRECTIONS (swap if motor goes wrong way) --
LEFT  = GPIO.LOW
RIGHT = GPIO.HIGH

# -- SETUP -----------------------------
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(DIR_PIN,   GPIO.OUT)
GPIO.setup(STEP_PIN,  GPIO.OUT)
GPIO.setup(LIMIT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
 
# -- STEP PULSE ------------------------
def step(delay=0.001):
    GPIO.output(STEP_PIN, GPIO.HIGH)
    time.sleep(delay)
    GPIO.output(STEP_PIN, GPIO.LOW)
    time.sleep(delay)

# -- MOVE FIXED STEPS ------------------
def move(steps, direction, delay=0.001):
    GPIO.output(DIR_PIN, direction)
    for _ in range(steps):
        step(delay)
 
# -- HOME: move LEFT until limit switch pressed --
def home():
    print("Moving left to limit switch...")
    GPIO.output(DIR_PIN, LEFT)
    while GPIO.input(LIMIT_PIN) == GPIO.HIGH:  # HIGH = not pressed
        step()
    print("Limit switch triggered. Stopped.")

# -- MAIN CYCLE ------------------------
def run():
    # 1. Go to home position
    home()
 
    # 2. Move right to petri dish loading position
    print("Moving to loading position...")
    move(10, RIGHT)
 
    # 3. Wait for user to place petri dish
    print("\n>> Place the petri dish now.")
    while input(">> Type 'ok' when done: ").strip().lower() != "ok":
        print(">> Please type 'ok' to confirm.")
 
    # 4. Move right to final position
    print("Moving to final position...")
    move(2200, RIGHT)
    print("Motor 1 cycle complete.")

# -- MAIN LOOP -------------------------
try:
    while True:
        print("\n1. Run   2. Exit")
        c = input("Choice: ").strip()
        if   c == "1": run()
        elif c == "2": break
 
except KeyboardInterrupt:
    print("\nStopped.")
finally:
    GPIO.cleanup()
