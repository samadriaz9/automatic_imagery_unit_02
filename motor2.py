import RPi.GPIO as GPIO
import time
 
# -- PINS ------------------------------
DIR_PIN   = 17
STEP_PIN  = 18
LIMIT_PIN = 6

# -- DIRECTIONS (swap if motor goes wrong way) --------
UP   = GPIO.HIGH
DOWN = GPIO.LOW
 
# -- SETUP -----------------------------
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(DIR_PIN,   GPIO.OUT)
GPIO.setup(STEP_PIN,  GPIO.OUT)
GPIO.setup(LIMIT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# -- FUNCTIONS -------------------------
def step(delay=0.001):
    GPIO.output(STEP_PIN, GPIO.HIGH)
    time.sleep(delay)
    GPIO.output(STEP_PIN, GPIO.LOW)
    time.sleep(delay)
 
def move(steps, direction, delay=0.001):
    GPIO.output(DIR_PIN, direction)
    for _ in range(steps):
        step(delay)
 
def home():
    # Move UP until limit switch is pressed
    print("Moving up to limit switch...")
    GPIO.output(DIR_PIN, UP)
    while GPIO.input(LIMIT_PIN) == GPIO.HIGH:  # HIGH = not pressed
        step()
    print("Limit switch triggered. Stopped.")
 
def run():
    home()            # go up to limit switch
    move(1000, DOWN)   # move down 1000 steps
    print("Cycle complete.")

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
