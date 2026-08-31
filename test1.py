import RPi.GPIO as GPIO
import time

GPIO.setmode(GPIO.BCM)
GPIO.setup(12, GPIO.OUT)
pwm = GPIO.PWM(12, 100)
pwm.start(0)

for duty in [60, 65]:
    print(f'Power: {duty}%')
    pwm.ChangeDutyCycle(duty)
    time.sleep(10)

pwm.ChangeDutyCycle(0)
time.sleep(1)
pwm.stop()
GPIO.cleanup()
