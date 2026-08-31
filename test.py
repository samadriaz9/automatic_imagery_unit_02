import RPi.GPIO as GPIO
import time

RELAY_PIN = 7   # GPIO7

GPIO.setmode(GPIO.BCM)

# Setup and FORCE OFF at start
GPIO.setup(RELAY_PIN, GPIO.OUT)
GPIO.output(RELAY_PIN, GPIO.HIGH)   # relay OFF
time.sleep(1)   # stabilize (important)

# -------- RELAY PULSE -------- #
def relay_pulse():
    GPIO.output(RELAY_PIN, GPIO.LOW)   # ON
    time.sleep(5)                      # stay ON for 5 sec
    GPIO.output(RELAY_PIN, GPIO.HIGH)  # OFF

# -------- CAMERA ON -------- #
def camera_on():
    print("Camera ON")
    relay_pulse()

# -------- CAMERA OFF -------- #
def camera_off():
    print("Camera OFF")
    relay_pulse()

# -------- CLEANUP -------- #
def cleanup():
    print("Cleaning GPIO")
    GPIO.cleanup()

# -------- MENU -------- #
try:
    while True:
        print("\n1. Camera ON")
        print("2. Camera OFF")
        print("3. Exit")

        choice = input("Enter: ")

        if choice == '1':
            camera_on()

        elif choice == '2':
            camera_off()

        elif choice == '3':
            break

        else:
            print("Invalid input")

except KeyboardInterrupt:
    pass

finally:
    cleanup()
