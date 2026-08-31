#!/usr/bin/env python3
"""
Single-dish imaging module.

Uses current hardware modules:
- camera slider: camera_module.py
- petri stage: petri_dishes.py

Call:
    start_imaging_capture_pattern(...)
to run the capture pattern and save images.
"""

import os
import io
import contextlib
import sys
import time

import cv2
import numpy as np

from camera_module import Camera_up, Camera_down
from petri_dishes import petri_dishes_up


class CameraDisconnectError(RuntimeError):
    """USB camera dropped during imaging; caller should home, incubate, and retry."""

    def __init__(self, message, dish=None, row=None, col=None):
        super().__init__(message)
        self.dish = dish
        self.row = row
        self.col = col


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def data_root():
    """Project ``data/`` folder next to the code (created if missing)."""
    base = os.path.dirname(os.path.abspath(__file__))
    return _ensure_dir(os.path.join(base, "data"))


def _next_exp_dir(output_root=None):
    """Create and return next sequential experiment folder: exp_01, exp_02, ..."""
    if output_root is None:
        output_root = data_root()
    output_root = _ensure_dir(output_root)
    idx = 1
    while True:
        name = f"exp_{idx:02d}"
        path = os.path.join(output_root, name)
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=False)
            return path
        idx += 1


def _open_usb_capture(device_index):
    """Open the USB camera; return None if the device cannot be opened."""
    idx = int(device_index)
    if sys.platform.startswith("linux"):
        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
    else:
        cap = cv2.VideoCapture(idx)
    if not cap.isOpened():
        try:
            cap.release()
        except Exception:
            pass
        return None
    return cap


def _capture_frame(cap, out_path, flush_frames=4, read_retries=5, square_crop=False):
    """Grab a fresh frame and save JPG (with retries for noisy streams)."""
    flush_frames = max(0, int(flush_frames))
    read_retries = max(1, int(read_retries))

    last_err = None
    for _ in range(read_retries):
        try:
            # Drop a few frames so we get something closer to current position.
            for _ in range(flush_frames):
                with contextlib.redirect_stderr(io.StringIO()):
                    cap.grab()
                time.sleep(0.01)

            with contextlib.redirect_stderr(io.StringIO()):
                ok, frame = cap.read()
            if not ok or frame is None:
                raise RuntimeError("USB camera frame read failed")

            if bool(square_crop):
                frame = _crop_center_square(frame)

            ok_write = cv2.imwrite(out_path, frame)
            if not ok_write:
                raise RuntimeError("cv2.imwrite failed")
            return
        except Exception as exc:
            last_err = exc
            time.sleep(0.05)

    raise RuntimeError(f"USB camera capture failed after retries: {last_err}")


def _crop_center_square(frame):
    """Crop a frame to a centered square (best-effort for square output)."""
    h, w = frame.shape[:2]
    side = min(w, h)
    x0 = int((w - side) / 2)
    y0 = int((h - side) / 2)
    return frame[y0 : y0 + side, x0 : x0 + side]


def _crop_center_fraction(img, fraction):
    """Keep the center ``fraction`` of width and height (e.g. 1/3 → middle third)."""
    f = float(fraction)
    if f >= 1.0 - 1e-6:
        return img
    if f <= 0:
        raise ValueError("fraction must be > 0")
    h, w = img.shape[:2]
    nh = max(1, int(round(h * f)))
    nw = max(1, int(round(w * f)))
    y0 = (h - nh) // 2
    x0 = (w - nw) // 2
    return img[y0 : y0 + nh, x0 : x0 + nw]


def _tile_index_rowmajor(row, col, ncols):
    """1-based linear index for row-major grid (row,col 0-based)."""
    return int(row) * int(ncols) + int(col) + 1


def _build_mosaic_from_tiles(
    output_dir,
    capture_rows,
    capture_cols,
    mosaic_rows,
    mosaic_cols,
    mosaic_window_row0=0,
    mosaic_window_col0=0,
    flip_x=False,
    flip_y=False,
    axis_swap=False,
    mosaic_center_fraction=1.0,
):
    """Stitch a mosaic from a rectangular window of captured tiles.

    Captures are ``1.jpg .. (capture_rows*capture_cols).jpg`` in row-major order.
    The mosaic uses tiles from capture cells
    (mosaic_window_row0 .. +mosaic_rows-1, mosaic_window_col0 .. +mosaic_cols-1).

    flip_x / flip_y / axis_swap: same layout fix as on hardware (swap+flipY for this rig).

    mosaic_center_fraction: if < 1, keep only the center fraction of each tile, then
        resize to the cell size (e.g. 1/3 to drop overlap when using a denser 7x7 scan).
    """
    capture_rows = int(capture_rows)
    capture_cols = int(capture_cols)
    mosaic_rows = int(mosaic_rows)
    mosaic_cols = int(mosaic_cols)
    wr0 = int(mosaic_window_row0)
    wc0 = int(mosaic_window_col0)
    if capture_rows <= 0 or capture_cols <= 0 or mosaic_rows <= 0 or mosaic_cols <= 0:
        raise ValueError("capture and mosaic rows/cols must be > 0")
    if wr0 < 0 or wc0 < 0:
        raise ValueError("mosaic window offset must be >= 0")
    if wr0 + mosaic_rows > capture_rows or wc0 + mosaic_cols > capture_cols:
        raise ValueError(
            f"mosaic window ({wr0}+{mosaic_rows}, {wc0}+{mosaic_cols}) "
            f"exceeds capture grid ({capture_rows}x{capture_cols})"
        )

    first_idx = _tile_index_rowmajor(wr0, wc0, capture_cols)
    first_path = os.path.join(output_dir, f"{first_idx}.jpg")
    first = cv2.imread(first_path)
    if first is None:
        raise RuntimeError(f"Could not read first mosaic source tile: {first_path}")

    tile_h, tile_w = first.shape[:2]
    tile_shape_tail = first.shape[2:] if len(first.shape) > 2 else ()

    out_rows = mosaic_cols if bool(axis_swap) else mosaic_rows
    out_cols = mosaic_rows if bool(axis_swap) else mosaic_cols
    mosaic = np.zeros((out_rows * tile_h, out_cols * tile_w) + tile_shape_tail, dtype=first.dtype)

    for mr in range(mosaic_rows):
        for mc in range(mosaic_cols):
            cap_r = wr0 + mr
            cap_c = wc0 + mc
            tile_idx = _tile_index_rowmajor(cap_r, cap_c, capture_cols)
            tile_path = os.path.join(output_dir, f"{tile_idx}.jpg")
            tile = cv2.imread(tile_path)
            if tile is None:
                raise RuntimeError(f"Could not read tile: {tile_path}")

            if tile.shape[0] != tile_h or tile.shape[1] != tile_w:
                tile = cv2.resize(tile, (tile_w, tile_h), interpolation=cv2.INTER_AREA)

            tile = _crop_center_fraction(tile, mosaic_center_fraction)
            if tile.shape[0] != tile_h or tile.shape[1] != tile_w:
                tile = cv2.resize(tile, (tile_w, tile_h), interpolation=cv2.INTER_CUBIC)

            if bool(axis_swap):
                base_r = mc
                base_c = mr
                max_r = mosaic_cols - 1
                max_c = mosaic_rows - 1
            else:
                base_r = mr
                base_c = mc
                max_r = mosaic_rows - 1
                max_c = mosaic_cols - 1

            dest_r = (max_r - base_r) if bool(flip_y) else base_r
            dest_c = (max_c - base_c) if bool(flip_x) else base_c

            y0 = dest_r * tile_h
            x0 = dest_c * tile_w
            mosaic[y0 : y0 + tile_h, x0 : x0 + tile_w] = tile

    return mosaic


def _trim_mosaic(mosaic, crop_top_px=0, crop_right_px=0):
    """Remove ``crop_top_px`` from the top and ``crop_right_px`` from the right."""
    ct = int(crop_top_px)
    cr = int(crop_right_px)
    if ct < 0 or cr < 0:
        raise ValueError("crop amounts must be >= 0")
    if ct == 0 and cr == 0:
        return mosaic
    h, w = mosaic.shape[:2]
    if h <= ct or w <= cr:
        raise ValueError(
            f"Mosaic size {w}x{h} too small to trim top={ct} and right={cr}"
        )
    return mosaic[ct:h, 0 : w - cr]


def _write_mosaic(output_dir, mosaic, mosaic_name):
    mosaic_path = os.path.join(output_dir, mosaic_name)
    ok = cv2.imwrite(mosaic_path, mosaic)
    if not ok:
        raise RuntimeError(f"Could not write mosaic: {mosaic_path}")
    return mosaic_path


def start_imaging_capture_pattern(
    output_root=None,
    experiment_dir=None,
    stage_subdir=None,
    camera_device_index=0,
    rows=8,
    cols=8,
    camera_step_per_col=85,
    petri_step_per_row=85,
    camera_reset_each_row=True,
    square_crop=True,
    save_mosaic=True,
    mosaic_name="mosaic.jpg",
    mosaic_center_fraction=1.0,
    mosaic_crop_top_px=600,
    mosaic_crop_right_px=600,
    settle_seconds=0.15,
):
    """
    Capture one petri dish in a matrix/raster grid pattern.

    Assumptions:
    - Current camera position is the start-of-row for column 0.
    - Current petri stage position is the start-of-grid for row 0.

    Motion:
    - Slide across each row by moving camera DOWN for each next column (after pre-position
      with Camera_up from home). Row end: petri dishes up, then camera UP back to column 0.
    - Shift to the next row by moving petri dishes towards "up".
    - Optionally reset camera back to column 0 after each row (needed to keep a square coverage area).

    ``camera_step_per_col`` and ``petri_step_per_row`` are independent (petri is no longer
    forced to match camera step).

    Capture grid is ``rows``×``cols`` (default 8×8 = 64 tiles). ``mosaic.jpg`` is a full ``rows``×``cols`` stitch
    (axis swap + flip Y for this rig). After assembly, ``mosaic_crop_top_px`` pixels are removed
    from the top and ``mosaic_crop_right_px`` from the right (default 600 each). Set both to 0 for
    no trim. ``mosaic_center_fraction`` uses only the center fraction of each tile before placing
    (default 1.0 = full tile).

    Returns:
        output_dir path containing captured images.
    """
    if experiment_dir:
        base_dir = _ensure_dir(experiment_dir)
    else:
        base_dir = _next_exp_dir(output_root)
    output_dir = _ensure_dir(os.path.join(base_dir, stage_subdir)) if stage_subdir else base_dir

    idx = int(camera_device_index)
    cap = _open_usb_capture(idx)
    if cap is None:
        raise CameraDisconnectError(
            f"Could not open USB camera index {idx} (/dev/video{idx}). "
            "Ensure no other code holds the device (stop preview threads first). "
            "If the device is not at video0, pass camera_device_index=..."
        )

    # Best-effort: request consistent resolution for decoding/saving.
    try:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    except Exception:
        pass

    try:
        row_step = int(petri_step_per_row)
        col_step = int(camera_step_per_col)

        total_tiles = int(rows) * int(cols)
        image_idx = 1
        for r in range(int(rows)):
            for c in range(int(cols)):
                img_name = f"{image_idx}.jpg"
                out_path = os.path.join(output_dir, img_name)
                print(f"[Imaging] Capture {image_idx}/{total_tiles} (row {r + 1}, col {c + 1})")
                try:
                    _capture_frame(cap, out_path, square_crop=bool(square_crop))
                except Exception as exc:
                    # USB stream can glitch after stepper motion; reopen once and retry.
                    print(f"[Imaging] Retry after capture error at ({r}, {c}): {exc}")
                    try:
                        cap.release()
                    except Exception:
                        pass
                    cap = _open_usb_capture(idx)
                    if cap is None:
                        raise CameraDisconnectError(
                            f"USB camera disconnected at row {r + 1}, col {c + 1}",
                            row=r,
                            col=c,
                        ) from exc
                    try:
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
                    except Exception:
                        pass
                    try:
                        _capture_frame(cap, out_path, square_crop=bool(square_crop))
                    except Exception as exc2:
                        raise CameraDisconnectError(
                            f"USB camera disconnected at row {r + 1}, col {c + 1}: {exc2}",
                            row=r,
                            col=c,
                        ) from exc2
                image_idx += 1
                time.sleep(settle_seconds)

                # Move camera for next column in this row (except last col).
                if c < cols - 1:
                    Camera_down(col_step)
                    time.sleep(settle_seconds)

            # End-of-row reposition
            if r < rows - 1:
                print(f"[Imaging] Next row: petri dishes UP {row_step} steps")
                petri_dishes_up(row_step)
                time.sleep(settle_seconds)

                # Reset camera to column 0 for the next row (keeps square coverage).
                if bool(camera_reset_each_row):
                    back_steps = int((cols - 1) * col_step)
                    if back_steps > 0:
                        Camera_up(back_steps)
                    time.sleep(settle_seconds)

        print(f"[Imaging] Capture complete: {output_dir}")
        if bool(save_mosaic):
            # Full capture grid mosaic; layout: axis swap + flip Y (swap_flipY for this rig).
            mosaic = _build_mosaic_from_tiles(
                output_dir=output_dir,
                capture_rows=int(rows),
                capture_cols=int(cols),
                mosaic_rows=int(rows),
                mosaic_cols=int(cols),
                mosaic_window_row0=0,
                mosaic_window_col0=0,
                flip_x=False,
                flip_y=True,
                axis_swap=True,
                mosaic_center_fraction=float(mosaic_center_fraction),
            )
            mosaic = _trim_mosaic(
                mosaic,
                crop_top_px=int(mosaic_crop_top_px),
                crop_right_px=int(mosaic_crop_right_px),
            )
            path = _write_mosaic(output_dir, mosaic, mosaic_name)
            print(f"[Imaging] Mosaic saved: {path}")
        return output_dir
    finally:
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass


def petri_dish_subdir(dish_number):
    """Subfolder name for one petri dish inside an experiment (1-based)."""
    return f"petri_{int(dish_number):02d}"


def start_multi_petri_imaging(
    num_petri_dishes=1,
    output_root=None,
    experiment_dir=None,
    petri_offset_per_dish=None,
    camera_offset_per_dish=None,
    tray_cols=5,
    petri_pre_up_row2=1400,
    camera_pre_up_row2=3730,
    rows=8,
    cols=8,
    camera_step_per_col=85,
    petri_step_per_row=85,
    settle_seconds=0.15,
    first_dish=1,
    last_dish=None,
    **capture_kwargs,
):
    """
    Run the same capture grid on 1–10 petri dishes in a tray (default 2×5).

    Dishes are numbered row-major: 1–5 = first row, 6–10 = second row.

    Dish 1 uses the stage/camera position caller already set before imaging.

    Dishes 2–5: petri DOWN (offset), camera DOWN (offset)—no homing.

    Dish 6 (first of second row): Camera_home(), petri_dishes_home(), then
    Camera_up(camera_pre_up_row2), petri_dishes_up(petri_pre_up_row2).

    Dishes 7–10: same incremental moves as 2–5.

    ``first_dish`` / ``last_dish`` (1-based, inclusive) limit which dishes are captured
    in this call. When ``first_dish`` is the first dish of row 2, row-2 homing runs first.

    One dish  → images in ``data/exp_XX/`` (no subfolder).
    N dishes  → ``data/exp_XX/petri_01/`` … ``petri_NN/``.

    Returns:
        Experiment directory path (parent of all petri subfolders).
    """
    from camera_module import Camera_home, Camera_up, Camera_down
    from petri_dishes import petri_dishes_home, petri_dishes_up, petri_dishes_down

    num = max(1, min(10, int(num_petri_dishes)))
    first_dish = max(1, min(num, int(first_dish)))
    last_dish = min(num, int(last_dish) if last_dish is not None else num)
    if first_dish > last_dish:
        raise ValueError(f"first_dish ({first_dish}) must be <= last_dish ({last_dish})")
    tc = max(1, int(tray_cols))
    row_step = int(petri_step_per_row)
    col_step = int(camera_step_per_col)
    petri_off = int(petri_offset_per_dish if petri_offset_per_dish is not None else row_step * 7)
    cam_off = int(camera_offset_per_dish if camera_offset_per_dish is not None else col_step)

    if experiment_dir:
        exp_dir = _ensure_dir(experiment_dir)
    else:
        exp_dir = _next_exp_dir(output_root)

    print(
        f"[Imaging] Multi-petri run: dishes {first_dish}-{last_dish} of {num}, "
        f"{tc} per row, exp={exp_dir}, "
        f"between dishes in a row: petri DOWN {petri_off}, camera DOWN {cam_off}; "
        f"row-2 start after homing: petri UP {int(petri_pre_up_row2)}, camera UP {int(camera_pre_up_row2)}"
    )

    pattern_kw = {
        "rows": int(rows),
        "cols": int(cols),
        "camera_step_per_col": col_step,
        "petri_step_per_row": row_step,
        "settle_seconds": float(settle_seconds),
    }
    pattern_kw.update(capture_kwargs)

    for dish in range(first_dish, last_dish + 1):
        print(f"[Imaging] ===== Petri dish {dish} / {num} =====")
        if dish == first_dish:
            if dish == tc + 1:
                print(
                    f"[Imaging] Row 2 start (dish {dish}): homing, then camera UP "
                    f"{int(camera_pre_up_row2)}, petri UP {int(petri_pre_up_row2)}"
                )
                Camera_home()
                petri_dishes_home()
                Camera_up(int(camera_pre_up_row2))
                petri_dishes_up(int(petri_pre_up_row2))
                time.sleep(float(settle_seconds))
        elif dish > first_dish:
            if dish == tc + 1:
                print(
                    f"[Imaging] Second row (dish {dish}): homing, then camera UP "
                    f"{int(camera_pre_up_row2)}, petri UP {int(petri_pre_up_row2)}"
                )
                Camera_home()
                petri_dishes_home()
                Camera_up(int(camera_pre_up_row2))
                petri_dishes_up(int(petri_pre_up_row2))
            else:
                print(
                    f"[Imaging] Next dish {dish}: petri DOWN {petri_off}, "
                    f"camera DOWN {cam_off}"
                )
                if petri_off > 0:
                    petri_dishes_down(petri_off)
                if cam_off > 0:
                    Camera_down(cam_off)
            time.sleep(float(settle_seconds))

        subdir = petri_dish_subdir(dish) if num > 1 else None
        try:
            out = start_imaging_capture_pattern(
                output_root=output_root,
                experiment_dir=exp_dir,
                stage_subdir=subdir,
                **pattern_kw,
            )
        except CameraDisconnectError as exc:
            exc.dish = dish
            raise
        print(f"[Imaging] Dish {dish} saved: {out}")

    return exp_dir

