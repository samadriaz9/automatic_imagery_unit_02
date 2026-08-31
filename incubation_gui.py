import tkinter as tk
from tkinter import messagebox
import threading
import time
import os
import glob
import RPi.GPIO as GPIO
from PIL import Image, ImageTk
from simple_pid import PID

# ---------- GPIO and PID Setup ----------
# GPIO Pins
RPWM = 18  # Pin number for cooling in BOARD mode
LPWM = 22  # Pin number for heating in BOARD mode

# Setup GPIO
GPIO.setup(RPWM, GPIO.OUT)
GPIO.setup(LPWM, GPIO.OUT)

pwm_r = GPIO.PWM(RPWM, 1000)
pwm_l = GPIO.PWM(LPWM, 1000)
pwm_r.start(0)
pwm_l.start(0)

# Setup DS18B20
base_dir = '/sys/bus/w1/devices/'
device_folder = glob.glob(base_dir + '28*')[0]
device_file = device_folder + '/w1_slave'

def read_temp_raw():
    with open(device_file, 'r') as f:
        return f.readlines()

def read_temp():
    lines = read_temp_raw()
    while lines[0].strip()[-3:] != 'YES':
        time.sleep(0.1)
        lines = read_temp_raw()
    equals_pos = lines[1].find('t=')
    if equals_pos != -1:
        temp_string = lines[1][equals_pos+2:]
        return float(temp_string) / 1000.0
    return None

# ---------- Calibration (Measured -> True) ----------
# Provide calibration pairs as (measured_sensor_celsius, true_standard_celsius)
# Update these points if you re-measure your system
CALIBRATION_POINTS = [
    (37.0, 38.0),
    (40.0, 42.0),
    (44.0, 47.0),
]

def calibrate_temperature(measured_value):
    """Convert raw sensor reading to calibrated true temperature using
    piecewise-linear interpolation/extrapolation over CALIBRATION_POINTS.
    """
    try:
        if measured_value is None:
            return None
        points = sorted(CALIBRATION_POINTS, key=lambda p: p[0])
        # If only one point, treat as constant offset
        if len(points) == 1:
            m, t = points[0]
            return measured_value + (t - m)
        # Below first point -> extrapolate using first segment
        if measured_value <= points[0][0]:
            m1, t1 = points[0]
            m2, t2 = points[1]
            slope = (t2 - t1) / (m2 - m1)
            return t1 + slope * (measured_value - m1)
        # Above last point -> extrapolate using last segment
        if measured_value >= points[-1][0]:
            m1, t1 = points[-2]
            m2, t2 = points[-1]
            slope = (t2 - t1) / (m2 - m1)
            return t1 + slope * (measured_value - m1)
        # Between points -> interpolate
        for i in range(1, len(points)):
            m1, t1 = points[i-1]
            m2, t2 = points[i]
            if m1 <= measured_value <= m2:
                slope = (t2 - t1) / (m2 - m1)
                return t1 + slope * (measured_value - m1)
        # Fallback: no change
        return measured_value
    except Exception:
        # On any error, return uncalibrated value to avoid breaking control
        return measured_value

def apply_pid_output(output):
    if output > 0:
        # Heating
        pwm_r.ChangeDutyCycle(0)
        pwm_l.ChangeDutyCycle(min(output, 100))
    elif output < 0:
        # Cooling
        pwm_l.ChangeDutyCycle(0)
        pwm_r.ChangeDutyCycle(min(-output, 100))
    else:
        # Neutral
        pwm_r.ChangeDutyCycle(0)
        pwm_l.ChangeDutyCycle(0)

# ---------- Simple Incubator GUI ----------
class IncubatorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Incubation Setup")
        BG_COLOR = "#2E3440"
        self.root.configure(bg=BG_COLOR)
    def __init__(self, root):
        self.root = root
        self.root.title("Incubation Setup")
        BG_COLOR = "#2E3440"
        self.root.configure(bg=BG_COLOR)

        # Remove the title bar (including the cross button)
        self.root.overrideredirect(True)

        # Set fullscreen mode
        self.root.attributes("-fullscreen", True)  # Enable fullscreen
        self.root.bind("<Escape>", self.exit_fullscreen)  # Allow exiting fullscreen with Escape key

        self.temperatures = [37 for _ in range(5)]
        self.durations = [1, 0, 0, 0, 0]
        self.running = False
        self.current_stage = 0
        self.remaining_time = 0
        self.pid_output = 0.0
        self.worker_thread = None

        self.temp_labels = []
        self.duration_labels = []
        self.slot_frames = []

        # --- Layout with left and right images ---
        container = tk.Frame(self.root, bg=BG_COLOR)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=0, minsize=480)
        container.columnconfigure(1, weight=1)
        container.columnconfigure(2, weight=0, minsize=500)
        container.rowconfigure(0, weight=1)

        # Left image
        try:
            left_img = Image.open("/home/ncai/Desktop/APP/image1.jpg")
        except:
            left_img = Image.new("RGB", (480, 1080), "gray")
        left_img = left_img.resize((480, 1080))
        self.left_photo = ImageTk.PhotoImage(left_img)
        left_label = tk.Label(container, image=self.left_photo, bg=BG_COLOR)
        left_label.grid(row=0, column=0, sticky="nsew")

        # Center controls (multi-stage, grid layout)
        main_frame = tk.Frame(container, padx=0, pady=10, bg=BG_COLOR)
        main_frame.grid(row=0, column=1, sticky="nsew")
        main_frame.columnconfigure(0, weight=1)
        for r in range(12):
            main_frame.rowconfigure(r, weight=1)

        # --- Coliform Preset Buttons (centered above Start/Stop) ---
        preset_frame = tk.Frame(main_frame, bg=BG_COLOR)
        preset_frame.grid(row=6, column=1, columnspan=3, pady=(0, 10))

        coliform_btn = tk.Button(
            preset_frame,
            text="ThermoTolerent Coliform",
            bg="#0055A4",
            fg="white",
            font=("Arial", 16, "bold"),
            width=22,
            command=self.set_thermotolerant_coliform
        )
        coliform_btn.pack(side="left", padx=10)

        total_coliform_btn = tk.Button(
            preset_frame,
            text="Total Coliform",
            bg="#A45500",
            fg="white",
            font=("Arial", 16, "bold"),
            width=18,
            command=self.set_total_coliform
        )
        total_coliform_btn.pack(side="left", padx=10)

        for i in range(5):
            slot_frame = tk.Frame(
                main_frame,
                borderwidth=5,
                relief="ridge",
                padx=18,
                pady=7,
                bg=BG_COLOR
            )
            # Place the slot frame in the middle by spanning center columns
            slot_frame.grid(row=i, column=1, columnspan=3, pady=5, sticky="ew", padx=(0, 0))
            self.slot_frames.append(slot_frame)

            # Temperature Controls
            tk.Button(
                slot_frame, text="-", width=5, height=2, font=("Arial", 24, "bold"),
                bg="#006400", fg="white",
                command=lambda idx=i: self.adjust_value(self.temperatures, idx, -1)
            ).grid(row=0, column=0, padx=(4, 4))

            temp_label = tk.Label(
                slot_frame, text=f"Temp: {self.temperatures[i]} °C", width=12,
                bg=BG_COLOR, fg="white", font=("Arial", 20, "bold")
            )
            temp_label.grid(row=0, column=1, padx=(4, 8))
            self.temp_labels.append(temp_label)

            tk.Button(
                slot_frame, text="+", width=5, height=2, font=("Arial", 24, "bold"),
                bg="#006400", fg="white",
                command=lambda idx=i: self.adjust_value(self.temperatures, idx, 1)
            ).grid(row=0, column=2, padx=(4, 8))

            # Time Controls
            tk.Button(
                slot_frame, text="-", width=5, height=2, font=("Arial", 24, "bold"),
                bg="#006400", fg="white",
                command=lambda idx=i: self.adjust_value(self.durations, idx, -1)
            ).grid(row=0, column=3, padx=(4, 4))

            dur_label = tk.Label(
                slot_frame, text=f"Time: {self.durations[i]} h", width=12,
                bg=BG_COLOR, fg="white", font=("Arial", 20, "bold")
            )
            dur_label.grid(row=0, column=4, padx=(4, 8))
            self.duration_labels.append(dur_label)

            tk.Button(
                slot_frame, text="+", width=5, height=2, font=("Arial", 24, "bold"),
                bg="#006400", fg="white",
                command=lambda idx=i: self.adjust_value(self.durations, idx, 1)
            ).grid(row=0, column=5, padx=(4, 4))

        main_frame.grid_rowconfigure(5, minsize=10)

        self.start_status_label = tk.Label(main_frame, text="", bg=BG_COLOR, fg="yellow", font=("Arial", 20, "bold"))
        # Span across all columns so it won't push buttons sideways
        self.start_status_label.grid(row=6, column=0, columnspan=5, pady=2, sticky="n")

        # Center Start and Stop buttons in the middle columns
        for c in range(5):
            main_frame.columnconfigure(c, weight=1)

        self.start_button = tk.Button(
            main_frame,
            text="Start",
            bg="green",
            fg="white",
            width=16,
            height=2,
            font=("Arial", 22, "bold"),
            command=self.start_incubation
        )
        self.start_button.grid(row=7, column=2, pady=4, padx=(10, 10))

        self.stop_button = tk.Button(
            main_frame,
            text="Stop",
            bg="red",
            fg="white",
            width=16,
            height=2,
            font=("Arial", 22, "bold"),
            command=self.stop_and_close  # Updated to stop and close the window
        )
        self.stop_button.grid(row=7, column=3, pady=4, padx=(10, 10))

        self.status_label = tk.Label(main_frame, text="Status: Idle", bg=BG_COLOR, fg="white", font=("Arial", 20, "bold"))
        self.status_label.grid(row=8, column=0, columnspan=7, pady=10)

        self.temp_display = tk.Label(main_frame, text="Current Temp: -- °C", bg=BG_COLOR, fg="white", font=("Arial", 20, "bold"))
        self.temp_display.grid(row=9, column=0, columnspan=7, pady=6)

        self.pid_display = tk.Label(main_frame, text="PID Output: --", bg=BG_COLOR, fg="white", font=("Arial", 20, "bold"))
        self.pid_display.grid(row=10, column=0, columnspan=7, pady=6)

        self.time_display = tk.Label(main_frame, text="Remaining Time: --:--:--", bg=BG_COLOR, fg="white", font=("Arial", 20, "bold"))
        self.time_display.grid(row=11, column=0, columnspan=7, pady=6)

        # Right image
        try:
            right_img = Image.open("/home/ncai/Desktop/APP/image2.jpg")
        except:
            right_img = Image.new("RGB", (500, 1080), "gray")
        right_img = right_img.resize((500, 1080))
        self.right_photo = ImageTk.PhotoImage(right_img)
        right_label = tk.Label(container, image=self.right_photo, bg=BG_COLOR)
        right_label.grid(row=0, column=2, sticky="nsew")

    def stop_and_close(self):
        """Stop the incubation process and close the window."""
        self.running = False
        apply_pid_output(0)  # Stop heating/cooling
        # Wait briefly for the worker thread to end to avoid updates after teardown
        try:
            if hasattr(self, 'worker_thread') and self.worker_thread is not None and self.worker_thread.is_alive():
                self.worker_thread.join(timeout=1.0)
        except Exception:
            pass

        try:
            if isinstance(self.root, tk.Toplevel):
                # Standalone window: fully cleanup
                try:
                    pwm_r.stop()
                    pwm_l.stop()
                except Exception:
                    pass
                try:
                    GPIO.cleanup()
                except Exception:
                    pass
                try:
                    self.root.destroy()
                except Exception:
                    pass
            else:
                # Embedded in main Tk root: leave app running
                try:
                    pwm_r.ChangeDutyCycle(0)
                    pwm_l.ChangeDutyCycle(0)
                except Exception:
                    pass
                try:
                    self.root.attributes("-fullscreen", False)
                except Exception:
                    pass
                try:
                    self.status_label.config(text="Status: Stopped")
                    self.start_button.config(bg="green")
                except Exception:
                    pass
        except Exception:
            pass

    def exit_fullscreen(self, event=None):
        """Exit fullscreen mode."""
        self.root.attributes("-fullscreen", False)

    def adjust_value(self, array, index, delta):
        array[index] += delta
        if array == self.temperatures:
            self.temp_labels[index].config(text=f"Temp: {array[index]} °C")
        elif array == self.durations:
            if array[index] < 0:
                array[index] = 0
            self.duration_labels[index].config(text=f"Time: {array[index]} h")

    def start_incubation(self):
        if self.running:
            messagebox.showinfo("Info", "Incubation is already running.")
            self.start_status_label.config(text="Incubation already in progress.")
            return

        self.schedule = []
        for i in range(5):
            temp = self.temperatures[i]
            duration = self.durations[i] * 3600
            if duration > 0:
                self.schedule.append((temp, duration))

        if not self.schedule:
            messagebox.showerror("Error", "Please select number of Hours.")
            # Keep UI consistent
            self.status_label.config(text="Status: Idle")
            self.start_status_label.config(text="Please select number of Hours.")
            return

        self.running = True
        self.current_stage = 0
        self.start_button.config(bg="green")
        self.start_status_label.config(text="Incubation Started.")
        self.worker_thread = threading.Thread(target=self.run_incubation, daemon=True)
        self.worker_thread.start()

    def stop_incubation(self):
        self.running = False
        self.status_label.config(text="Status: Stopped")
        self.start_button.config(bg="green")
        apply_pid_output(0)  # Stop heating/cooling

    def run_incubation(self):
        while self.running and self.current_stage < len(self.schedule):
            target_temp, duration = self.schedule[self.current_stage]
            self.remaining_time = duration

            # Setup PID for this stage
            pid = PID(Kp=10.0, Ki=0.2, Kd=2.0, setpoint=target_temp)
            pid.output_limits = (-100, 100)

            def set_stage_status():
                try:
                    self.status_label.config(text=f"Stage {self.current_stage+1}: Maintaining {target_temp}°C")
                    self.highlight_slot(self.current_stage)
                except Exception:
                    pass
            try:
                self.root.after(0, set_stage_status)
            except Exception:
                pass

            while self.remaining_time > 0 and self.running:
                current_temp_raw = read_temp()
                current_temp = calibrate_temperature(current_temp_raw)
                def update_temp():
                    try:
                        if current_temp is not None and current_temp_raw is not None:
                            self.temp_display.config(text=f"Current Temp (cal): {current_temp:.2f} °C  |  Raw: {current_temp_raw:.2f} °C")
                        else:
                            self.temp_display.config(text=f"Current Temp (cal): {current_temp} °C  |  Raw: {current_temp_raw} °C")
                    except Exception:
                        pass
                try:
                    self.root.after(0, update_temp)
                except Exception:
                    pass

                control = pid(current_temp)
                self.pid_output = control
                def update_pid():
                    try:
                        self.pid_display.config(text=f"PID Output: {control:.2f}")
                    except Exception:
                        pass
                try:
                    self.root.after(0, update_pid)
                except Exception:
                    pass
                apply_pid_output(control)

                hours, remainder = divmod(self.remaining_time, 3600)
                minutes, seconds = divmod(remainder, 60)
                def update_time():
                    try:
                        self.time_display.config(text=f"Remaining Time: {int(hours):02}:{int(minutes):02}:{int(seconds):02}")
                    except Exception:
                        pass
                try:
                    self.root.after(0, update_time)
                except Exception:
                    pass

                time.sleep(2)
                self.remaining_time -= 2

            self.current_stage += 1

        def finish_status():
            try:
                self.status_label.config(text="Status: Incubation Complete")
                self.start_button.config(bg="red")
                self.highlight_slot(None)
            except Exception:
                pass
        try:
            self.root.after(0, finish_status)
        except Exception:
            pass
        self.running = False
        apply_pid_output(0)  # Ensure OFF

    def highlight_slot(self, active_index):
        for i, frame in enumerate(self.slot_frames):
            if i == active_index:
                frame.config(bg="#006400")
            else:
                frame.config(bg=self.root.cget("bg"))

    def set_thermotolerant_coliform(self):
        # 1. 30°C for 4h, 2. 44°C for 18h, rest 37°C/0h
        self.temperatures = [30, 44, 37, 37, 37]
        self.durations = [4, 18, 0, 0, 0]
        for i in range(5):
            self.temp_labels[i].config(text=f"Temp: {self.temperatures[i]} °C")
            self.duration_labels[i].config(text=f"Time: {self.durations[i]} h")

    def set_total_coliform(self):
        # 1. 30°C for 4h, 2. 37°C for 18h, rest 37°C/0h
        self.temperatures = [30, 37, 37, 37, 37]
        self.durations = [4, 18, 0, 0, 0]
        for i in range(5):
            self.temp_labels[i].config(text=f"Temp: {self.temperatures[i]} °C")
            self.duration_labels[i].config(text=f"Time: {self.durations[i]} h")


if __name__ == "__main__":
    root = tk.Tk()
    app = IncubatorGUI(root)
    root.mainloop()