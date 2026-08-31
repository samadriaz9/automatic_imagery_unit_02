import RPi.GPIO as GPIO
import glob
import time
import os
 
# -- PINS ------------------------------
RPWM_PIN = 12   # BCM 12 ? Physical Pin 32

# -- SENSOR SETUP ----------------------
base_dir = '/sys/bus/w1/devices/'
device_folder = glob.glob(base_dir + '28*')[0]
device_file = device_folder + '/w1_slave'

# -- GPIO SETUP ------------------------
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(RPWM_PIN, GPIO.OUT)
pwm = GPIO.PWM(RPWM_PIN, 100)  # 100 Hz - smoother for heater
pwm.start(0)
 
current_duty = 0  # track current duty cycle

# -- READ TEMPERATURE ------------------
def read_temp():
    try:
        f = open(device_file, 'r')
        lines = f.readlines()
        f.close()
        if lines[0].strip()[-3:] != 'YES':
            return None
        return float(lines[1].split('t=')[1]) / 1000.0
    except:
        return None

# -- SOFT START - slowly increase power -
def set_power(target_duty):
    global current_duty
    target_duty = min(target_duty, 50)  # never go above 50%
    step = 2 if target_duty > current_duty else -2
    for d in range(int(current_duty), int(target_duty) + step, step):
        d = max(0, min(50, d))
        pwm.ChangeDutyCycle(d)
        time.sleep(0.1)  # slow ramp
    current_duty = target_duty

def heater_on():
    set_power(50)
 
def heater_off():
    set_power(0)

# -- MAIN PROGRAM ----------------------
def run(target_temp):
    print(f"\nTarget: {target_temp} C -- Press Ctrl+C to stop\n")
    time.sleep(1)
    while True:
        temp = read_temp()
        os.system('clear')

        print("=" * 35)
        print("       HEATER CONTROLLER")
        print("=" * 35)

        if temp is not None:
            print(f"  Current Temp : {round(temp, 2)} C")
            print(f"  Target Temp  : {target_temp} C")
            print(f"  PWM Power    : {current_duty} %")
            print("-" * 35)

            if temp < target_temp - 1:     # 1 degree buffer
                heater_on()
                print("  Heater       : ON  ??")
            elif temp >= target_temp:
                heater_off()
                print("  Heater       : OFF ")
            else:
                print("  Heater       : HOLDING...")
        else:
            heater_off()
            print("  Sensor ERROR  heater OFF!")
 
        print("=" * 35)
        time.sleep(2)

# -- MAIN MENU -------------------------
try:
    while True:
        print("\n1. Start Heater   2. Exit")
        c = input("Choice: ").strip()

        if c == "1":
            try:
                target = float(input("Set target temperature (C): "))
                run(target)
            except ValueError:
                print("Invalid! Enter a number like 37")
        elif c == "2":
            break

except KeyboardInterrupt:
    print("\nStopped.")
 
finally:
    heater_off()
    pwm.stop()
    GPIO.cleanup()
    print("Heater OFF. Goodbye!")

# -- MAIN LOOP -------------------------
try:
    while True:
        print("\n1. Start Heater   2. Exit")
        c = input("Choice: ").strip()

        if c == "1":
            try:
                target = float(input("Set target temperature (C): "))
                run(target)
            except ValueError:
                print("Invalid temperature! Enter a number.")

        elif c == "2":
            break
 
except KeyboardInterrupt:
    print("\nStopped.")
 
finally:
    heater_off()
    pwm.stop()
    GPIO.cleanup()
    print("Heater OFF. Goodbye!")
