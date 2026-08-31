"""
USB camera preview test utility.

Opens a single USB webcam by index, shows live video in a window, and provides
a Close button (and releases the device on window exit).

Run from the project directory:
    python camera_test.py
    python camera_test.py --device 1
"""
import argparse
import contextlib
import io
import sys
import threading
import time
import tkinter as tk
from typing import Optional
from tkinter import messagebox, ttk

import cv2
from PIL import Image, ImageTk


def open_usb_capture(device_index: int) -> Optional[cv2.VideoCapture]:
    """Open a USB camera using the same backend choice as usb_camera_thread."""
    idx = int(device_index)
    if sys.platform.startswith("linux"):
        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
    else:
        cap = cv2.VideoCapture(idx)
    if not cap.isOpened():
        return None
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    return cap


class USBCameraTestApp:
    def __init__(self, root: tk.Tk, device_index: int, max_preview_width: int = 960):
        self.root = root
        self.device_index = int(device_index)
        self.max_preview_width = int(max_preview_width)

        self._cap: cv2.VideoCapture | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest = None
        self._reader: threading.Thread | None = None
        self._photo = None

        self.root.title(f"USB camera test (device {self.device_index})")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        main = ttk.Frame(root, padding=8)
        main.pack(fill=tk.BOTH, expand=True)

        self._label = ttk.Label(main)
        self._label.pack(fill=tk.BOTH, expand=True)

        btn_row = ttk.Frame(main)
        btn_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(btn_row, text="Close", command=self._on_close).pack(side=tk.RIGHT)

        self._cap = open_usb_capture(self.device_index)
        if self._cap is None:
            messagebox.showerror(
                "Camera",
                f"Could not open USB camera at index {self.device_index}.\n"
                "Try another index with: python camera_test.py --device N",
            )
            root.after(100, root.destroy)
            return

        self._reader = threading.Thread(target=self._capture_loop, daemon=True)
        self._reader.start()
        self._schedule_update()

    def _capture_loop(self):
        cap = self._cap
        if cap is None:
            return
        while not self._stop.is_set():
            if sys.platform.startswith("linux"):
                with contextlib.redirect_stderr(io.StringIO()):
                    ok, frame = cap.read()
            else:
                ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            with self._lock:
                self._latest = frame

    def _schedule_update(self):
        if self._stop.is_set():
            return
        self._update_preview()
        self.root.after(30, self._schedule_update)

    def _update_preview(self):
        with self._lock:
            frame = self._latest
        if frame is None:
            return

        h, w = frame.shape[:2]
        if w > self.max_preview_width and w > 0:
            scale = self.max_preview_width / float(w)
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        self._photo = ImageTk.PhotoImage(image=img)
        self._label.configure(image=self._photo)

    def _on_close(self):
        self._stop.set()
        if self._reader is not None:
            self._reader.join(timeout=3.0)
            self._reader = None
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        self.root.destroy()


def main() -> int:
    p = argparse.ArgumentParser(description="USB camera preview test (OpenCV index).")
    p.add_argument(
        "--device",
        "-d",
        type=int,
        default=0,
        help="Camera device index (default: 0). On Linux this is typically /dev/videoN.",
    )
    p.add_argument(
        "--max-width",
        type=int,
        default=960,
        help="Maximum preview width in pixels (default: 960).",
    )
    args = p.parse_args()

    root = tk.Tk()
    USBCameraTestApp(root, device_index=args.device, max_preview_width=args.max_width)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
