import glob
import time
import os

base_dir = '/sys/bus/w1/devices/'
device_folder = glob.glob(base_dir + '28*')[0]
device_file = device_folder + '/w1_slave'

def read_temp():
    f = open(device_file, 'r')
    lines = f.readlines()
    f.close()

    if lines[0].strip()[-3:] != 'YES':
        return None

    temp_line = lines[1]
    temp = float(temp_line.split('t=')[1]) / 1000.0
    return temp

while True:
    temp = read_temp()
    
    os.system('clear')   # clears screen

    print("TEMPERATURE MONITOR")
    print("-------------------")

    if temp:
        print("Temperature:", round(temp, 2), "C")
    else:
        print("Sensor error")

    time.sleep(1)
