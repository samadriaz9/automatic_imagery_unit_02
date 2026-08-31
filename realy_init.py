import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BCM)
GPIO.setup(7, GPIO.OUT, initial=GPIO.HIGH)  # OFF state
