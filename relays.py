"""
Main script for Filteration Flask, Filteration Unit and Suction Pump control.
Runs homing (down until limit switch via PCF8574) and then movements.

Filteration flask: STEP=18, DIR=23 (BCM); EN tied on hardware (see filteration_flask.py).
Filteration unit: STEP=13, DIR=19 (BCM); EN tied on hardware (see filteration_unit.py).
Suction pump lift (stepper): STEP=21, DIR=12 (BCM); EN tied on hardware (see suction_pump_up_down.py). Flask DC pump: upper_suction_pump.py.
Petri dishes: STEP=10, DIR=22 (BCM); EN tied on hardware (see petri_dishes.py).
"""
from filteration_flask import (
    Filteration_flask_up,
    Filteration_flask_down,
    filteration_flask_config,
    cleanup as filteration_cleanup,
)
from filteration_unit import (
    Filteration_unit_up,
    Filteration_unit_down,
    filteration_unit_config,
    cleanup as filteration_unit_cleanup,
)
from upper_suction_pump import cleanup as suction_cleanup
from consumables import (consumable_up,
    consumable_down)
import RPi.GPIO as GPIO
import time

try:
    
    # Filteration unit: move down until limit switch on P2 (PCF8574) is pressed
    #filteration_unit_config()
    #Filteration_unit_up(200)
    # Filteration flask: move down until limit switch on P0 (PCF8574) is pressed
    #filteration_flask_config()
    #Filteration_flask_up(1150)

    # Suction pump: move down until limit switch on P1 (PCF8574) is pressed
    #suction_pump_config()
    #Suction_pump_up(1000)
    
    consumable_up(1000)
    consumable_down(1000)
finally:
    # Clean up all modules
    filteration_cleanup()
    filteration_unit_cleanup()
    suction_cleanup()
    GPIO.cleanup()
