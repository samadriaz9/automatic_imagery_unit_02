"""
Six-step automation workflow — callable from CLI (main.py) or procedure_gui.py.
"""

import os
import time

from device_config import (
    CAMERA_DISCONNECT_MAX_RECOVERIES,
    CAMERA_DISCONNECT_RECOVERY_MIN,
    CAMERA_DISCONNECT_RECOVERY_TEMP_C,
    CAMERA_DISH_PRE_UP,
    CAMERA_DISH_PRE_UP_ROW2,
    CAMERA_STEPSIZE,
    DEFAULT_ROUND_ENABLED,
    DEFAULT_ROUND_TEMPS,
    DEFAULT_ROUND_TIMES_MIN,
    DISHES_PER_TRAY_ROW,
    IMAGING_COLS,
    IMAGING_ROWS,
    MAX_PETRI_DISHES,
    MID_ROW_IMAGING_MIN,
    MID_ROW_IMAGING_TEMP_C,
    NUM_INCUBATION_SLOTS,
    NUM_STUDY_ROUNDS,
    STEP_INCUBATION_MINUTES,
    STEP_INCUBATION_TEMP_C,
    PETRI_DISH_PRE_UP,
    PETRI_DISH_PRE_UP_ROW2,
    PETRI_STEPSIZE,
    PETRI_TRAY_COLS,
)
from camera_module import Camera_down, Camera_home, Camera_up
from incubator_lid import incubator_lid_down, incubator_lid_home
from incubation_module import (
    Start_incubation,
    UPPER_HEATER_PIN,
    release_incubation_heaters,
)
from imaging import CameraDisconnectError, _next_exp_dir, data_root, start_multi_petri_imaging
from petri_dishes import petri_dishes_down, petri_dishes_home, petri_dishes_up


def step_01_all_home():
    """Step 1: All modules home."""
    Camera_home()
    incubator_lid_home()
    petri_dishes_home()
    petri_dishes_up(2370)
    incubator_lid_down(700)


def step_02_insert_petri_dishes():
    """Step 2: Open lid and move the tray out to the loading position."""
    incubator_lid_home()
    petri_dishes_up(2370)


def step_03_shift_for_incubation():
    """Step 3: Shift stage for incubation region."""
    incubator_lid_home()
    petri_dishes_home()
    petri_dishes_up(2370)
    incubator_lid_down(700)


def step_04_incubation(on_tick=None):
    """Step 4: Hold sample at 37 °C for 2 minutes."""
    print(
        f"[Step 4] Incubation {STEP_INCUBATION_TEMP_C:g}°C "
        f"for {STEP_INCUBATION_MINUTES:g} min"
    )
    Start_incubation(
        STEP_INCUBATION_TEMP_C,
        STEP_INCUBATION_MINUTES,
        on_tick=on_tick,
    )


def step_05_prepare_imaging():
    """Step 5a: Move to imaging start (before camera / capture)."""
    incubator_lid_home()
    petri_dishes_home()
    petri_dishes_up(PETRI_DISH_PRE_UP)
    Camera_home()
    Camera_up(CAMERA_DISH_PRE_UP)


def step_05_post_imaging_cleanup():
    """Step 5b: Park after imaging."""
    incubator_lid_home()
    petri_dishes_home()
    petri_dishes_up(2370)
    incubator_lid_down(700)


def step_06_sterilize():
    """Step 6: Return incubator and petri to home."""
    incubator_lid_home()
    petri_dishes_home()


def step_05_prepare_imaging_row2():
    """Move to imaging start for tray row 2 (petri dishes 6–10)."""
    incubator_lid_home()
    petri_dishes_home()
    Camera_home()
    Camera_up(CAMERA_DISH_PRE_UP_ROW2)
    petri_dishes_up(PETRI_DISH_PRE_UP_ROW2)


def _run_multi_petri_capture(num, capture_root, first_dish, last_dish):
    start_multi_petri_imaging(
        num_petri_dishes=num,
        experiment_dir=capture_root,
        tray_cols=PETRI_TRAY_COLS,
        petri_pre_up_row2=PETRI_DISH_PRE_UP_ROW2,
        camera_pre_up_row2=CAMERA_DISH_PRE_UP_ROW2,
        petri_offset_per_dish=PETRI_STEPSIZE * 7,
        camera_offset_per_dish=CAMERA_STEPSIZE,
        rows=IMAGING_ROWS,
        cols=IMAGING_COLS,
        camera_step_per_col=CAMERA_STEPSIZE,
        petri_step_per_row=PETRI_STEPSIZE,
        first_dish=first_dish,
        last_dish=last_dish,
    )


def _log_msg(msg, on_log=None):
    print(msg)
    if on_log:
        on_log(msg)


def _prepare_imaging_for_dish(dish):
    """Home and move to the start position of a 1-based dish (after recovery)."""
    dish = max(1, int(dish))
    petri_off = PETRI_STEPSIZE * 7
    cam_off = CAMERA_STEPSIZE
    if dish <= DISHES_PER_TRAY_ROW:
        step_05_prepare_imaging()
        skips = dish - 1
    else:
        step_05_prepare_imaging_row2()
        skips = dish - DISHES_PER_TRAY_ROW - 1
    for _ in range(skips):
        if petri_off > 0:
            petri_dishes_down(petri_off)
        if cam_off > 0:
            Camera_down(cam_off)


def _recover_from_camera_disconnect(on_tick=None, on_log=None):
    """Park at incubation pose, hold 5 min, so imaging can be retried from home."""
    _log_msg(
        "[Recovery] Camera disconnected during imaging — returning all home",
        on_log,
    )
    step_01_all_home()
    _log_msg(
        f"[Recovery] Incubation {CAMERA_DISCONNECT_RECOVERY_TEMP_C:g}°C "
        f"for {CAMERA_DISCONNECT_RECOVERY_MIN:g} min, then retry",
        on_log,
    )
    Start_incubation(
        CAMERA_DISCONNECT_RECOVERY_TEMP_C,
        CAMERA_DISCONNECT_RECOVERY_MIN,
        on_tick=on_tick,
    )


def capture_petri_dishes(
    num_petri_dishes,
    experiment_dir=None,
    time_point_subdir=None,
    on_tick=None,
    on_log=None,
):
    """
    Power on camera if needed, run multi-petri capture, power off camera.

    With 10 dishes: row 1 (dishes 1–5) → all home → 4 min upper-only incubation
    at 37 °C → row 2 (dishes 6–10). All images go to the same experiment folder.

    If the USB camera disconnects mid-capture: all home, incubate 5 min at 37 °C,
    then retry from the dish that failed.

    Returns experiment directory path used for captures.
    """
    from main import ensure_usb_camera_ready, power_off_usb_camera

    num = max(1, min(MAX_PETRI_DISHES, int(num_petri_dishes)))
    if experiment_dir is None:
        experiment_dir = _next_exp_dir(data_root())
    capture_root = experiment_dir
    if time_point_subdir:
        capture_root = os.path.join(experiment_dir, str(time_point_subdir))
        os.makedirs(capture_root, exist_ok=True)

    split_rows = num == MAX_PETRI_DISHES and num == DISHES_PER_TRAY_ROW * 2
    row1_end = DISHES_PER_TRAY_ROW
    row2_start = DISHES_PER_TRAY_ROW + 1
    recoveries = 0
    resume_dish = 1

    def _capture_from(start_dish):
        if split_rows:
            if start_dish <= row1_end:
                print(
                    f"[Imaging] Split capture: row 1 (dishes {start_dish}-{row1_end}), "
                    f"mid incubation, row 2 (dishes {row2_start}-{num})"
                )
                _run_multi_petri_capture(num, capture_root, start_dish, row1_end)
                print("[Imaging] Row 1 complete — all home before mid-row incubation")
                step_01_all_home()
                print(
                    f"[Imaging] Mid-row incubation: {MID_ROW_IMAGING_TEMP_C:g}°C "
                    f"for {MID_ROW_IMAGING_MIN:g} min (upper heater only)"
                )
                Start_incubation(
                    MID_ROW_IMAGING_TEMP_C,
                    MID_ROW_IMAGING_MIN,
                    on_tick=on_tick,
                    heater_pins=(UPPER_HEATER_PIN,),
                )
                step_05_prepare_imaging_row2()
                _run_multi_petri_capture(num, capture_root, row2_start, num)
            else:
                _run_multi_petri_capture(num, capture_root, start_dish, num)
        else:
            _run_multi_petri_capture(num, capture_root, start_dish, num)

    try:
        while True:
            try:
                if recoveries > 0:
                    _log_msg(
                        f"[Recovery] Repositioning to petri dish {resume_dish} and retrying",
                        on_log,
                    )
                    _prepare_imaging_for_dish(resume_dish)
                ready, _relay_used = ensure_usb_camera_ready(device_index=0)
                if not ready:
                    raise CameraDisconnectError("USB camera not available")
                _capture_from(resume_dish)
                break
            except CameraDisconnectError as exc:
                recoveries += 1
                failed = int(exc.dish) if getattr(exc, "dish", None) else resume_dish
                if recoveries > CAMERA_DISCONNECT_MAX_RECOVERIES:
                    raise RuntimeError(
                        f"USB camera still disconnected after "
                        f"{CAMERA_DISCONNECT_MAX_RECOVERIES} recoveries "
                        f"(last dish {failed}): {exc}"
                    ) from exc
                _log_msg(
                    f"[Recovery] Disconnect at dish {failed} "
                    f"({recoveries}/{CAMERA_DISCONNECT_MAX_RECOVERIES}): {exc}",
                    on_log,
                )
                _recover_from_camera_disconnect(on_tick=on_tick, on_log=on_log)
                resume_dish = failed
    finally:
        power_off_usb_camera()

    return experiment_dir


def run_timed_picture_study(
    num_petri_dishes,
    num_rounds,
    interval_minutes,
    target_c=None,
    on_tick=None,
    on_log=None,
):
    """
    Incubate for each interval, then capture all petri dishes.

    Folders: ``data/exp_XX/03min/``, ``data/exp_XX/06min/`` (cumulative minutes).

    ``interval_minutes``: minutes per round (first ``num_rounds`` used, max ``NUM_STUDY_ROUNDS``).

    Returns parent experiment directory.
    """
    if target_c is None:
        target_c = DEFAULT_ROUND_TEMPS[0]

    num_rounds = max(1, min(NUM_STUDY_ROUNDS, int(num_rounds)))
    intervals = list(interval_minutes)[:NUM_STUDY_ROUNDS]
    while len(intervals) < NUM_STUDY_ROUNDS:
        intervals.append(intervals[-1] if intervals else 3)

    exp_dir = _next_exp_dir(data_root())
    cumulative = 0.0

    def _log(msg):
        print(msg)
        if on_log:
            on_log(msg)

    for rnd in range(1, num_rounds + 1):
        mins = float(intervals[rnd - 1])
        cumulative += mins
        label = f"{int(round(cumulative)):02d}min"
        _log(f"Round {rnd}/{num_rounds}: incubate {mins:g} min → capture → {label}/")

        Start_incubation(float(target_c), mins, on_tick=on_tick)

        step_05_prepare_imaging()
        capture_petri_dishes(
            num_petri_dishes,
            experiment_dir=exp_dir,
            time_point_subdir=label,
            on_tick=on_tick,
            on_log=on_log,
        )

    step_05_post_imaging_cleanup()
    _log(f"Timed study complete: {exp_dir}")
    return exp_dir


def run_incubation_imaging_study(
    num_petri_dishes,
    round_temps,
    round_times_min,
    rounds_enabled=None,
    on_tick=None,
    on_log=None,
    on_round_start=None,
):
    """
    For each enabled round: incubate at round temp/time, then capture petri dishes.

    Images are saved under ``data/exp_XX/{MM}min/`` using that round's time (minutes).
    Duplicate folder names get a ``_rN`` suffix.
    """
    temps = [float(t) for t in round_temps[:NUM_STUDY_ROUNDS]]
    times = [float(t) for t in round_times_min[:NUM_STUDY_ROUNDS]]
    enabled = list(rounds_enabled or DEFAULT_ROUND_ENABLED)
    while len(temps) < NUM_STUDY_ROUNDS:
        temps.append(37.0)
    while len(times) < NUM_STUDY_ROUNDS:
        times.append(4.0)
    while len(enabled) < NUM_STUDY_ROUNDS:
        enabled.append(False)

    if not any(enabled[:NUM_STUDY_ROUNDS]):
        raise ValueError("Enable at least one round")

    exp_dir = _next_exp_dir(data_root())

    def _log(msg):
        print(msg)
        if on_log:
            on_log(msg)

    active = [i + 1 for i in range(NUM_STUDY_ROUNDS) if enabled[i]]
    _log(f"Incubation + imaging: {len(active)} round(s), petri={num_petri_dishes}")

    try:
        for idx, rnd in enumerate(active):
            temp = temps[rnd - 1]
            mins = times[rnd - 1]
            label = f"{int(round(mins)):02d}min"
            subdir = label
            if os.path.exists(os.path.join(exp_dir, subdir)):
                subdir = f"{label}_r{rnd}"

            is_final_round = idx == len(active) - 1
            _log(f"  Round {rnd}: {temp:g}°C, {mins:g} min → capture → {subdir}/")
            if on_round_start:
                try:
                    on_round_start(rnd)
                except Exception:
                    pass

            Start_incubation(
                temp,
                mins,
                on_tick=on_tick,
                keep_upper_heater_on_exit=not is_final_round,
            )
            step_05_prepare_imaging()
            capture_petri_dishes(
                num_petri_dishes,
                experiment_dir=exp_dir,
                time_point_subdir=subdir,
                on_tick=on_tick,
                on_log=on_log,
            )
            release_incubation_heaters()

            if not is_final_round:
                next_rnd = active[idx + 1]
                _log(f"  Round {rnd} complete — all home before round {next_rnd}")
                step_01_all_home()
    finally:
        release_incubation_heaters()

    step_05_post_imaging_cleanup()
    _log(f"Incubation + imaging complete: {exp_dir}")
    return exp_dir
