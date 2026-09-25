import glob
import time
import RPi.GPIO as GPIO

try:
    from simple_pid import PID
except Exception:
    PID = None


LOWER_HEATER_PIN = 26  # BCM 26, physical pin 37
UPPER_HEATER_PIN = 12  # BCM 12, physical pin 32
UPPER_HEATER_DUTY_BOOST = 1.30  # upper runs 30% hotter than lower (same PID base)
# Last N minutes of a long hold: both heaters OFF so dishes cool before imaging
# (avoids condensation). Holds ≤ this length heat fully, then add this cool-down.
PRE_IMAGING_COOL_DOWN_MIN = 5.0
# Legacy alias used by older call sites / docs.
LOWER_HEATER_OFF_REMAINING_MIN = PRE_IMAGING_COOL_DOWN_MIN
# Manual heater self-test (GUI buttons).
HEATER_TEST_DUTY = 50.0
HEATER_TEST_MINUTES = 5.0
HEATER_TEST_PWM_FREQ = 100
UPPER_HEATER_TEST_DUTY = HEATER_TEST_DUTY
UPPER_HEATER_TEST_MINUTES = HEATER_TEST_MINUTES
UPPER_HEATER_TEST_PWM_FREQ = HEATER_TEST_PWM_FREQ
LOWER_HEATER_TEST_DUTY = HEATER_TEST_DUTY
LOWER_HEATER_TEST_MINUTES = HEATER_TEST_MINUTES
LOWER_HEATER_TEST_PWM_FREQ = HEATER_TEST_PWM_FREQ
# Once sample is this many °C below target, lower stays off (upper finishes ramp).
# Example: target 37 °C → lower off from 34 °C onward to reduce lid vapour.
LOWER_HEATER_OFF_BELOW_TARGET_C = 3.0
HEATER_DUTY_SCALE = {
    LOWER_HEATER_PIN: 1.0,
    UPPER_HEATER_PIN: UPPER_HEATER_DUTY_BOOST,
}
DEFAULT_HEATER_PINS = (LOWER_HEATER_PIN, UPPER_HEATER_PIN)
# Legacy alias (first / lower heater)
RPWM_PIN = LOWER_HEATER_PIN

_held_upper_channels = []
_test_heater_channels = []
_heater_test_stop = False


def _stop_channel(ch):
    try:
        ch["pwm"].ChangeDutyCycle(0)
        ch["pwm"].stop()
    except Exception:
        pass


def stop_heater_test():
    """Force-stop any running heater self-test and release its PWM."""
    global _heater_test_stop, _test_heater_channels
    _heater_test_stop = True
    if not _test_heater_channels:
        return
    for ch in list(_test_heater_channels):
        _stop_channel(ch)
    _test_heater_channels = []
    print("[Incubation] Heater test stopped — upper heater OFF.")


def release_incubation_heaters():
    """Turn off held upper heater and any heater self-test outputs."""
    global _held_upper_channels
    stop_heater_test()
    if not _held_upper_channels:
        return
    for ch in list(_held_upper_channels):
        _stop_channel(ch)
    _held_upper_channels = []
    print("[Incubation] Held upper heater OFF.")


def _stop_heater_channels(channels, pins_to_stop=None):
    stop_pins = pins_to_stop
    if stop_pins is None:
        stop_pins = {ch["pin"] for ch in channels}
    for ch in channels:
        if ch["pin"] in stop_pins:
            _stop_channel(ch)


def _read_ds18b20_c(sensor_glob="/sys/bus/w1/devices/28-*/w1_slave"):
    """
    Read DS18B20 temperature in Celsius from w1 sysfs.
    Raises RuntimeError if sensor file is missing or CRC/data invalid.
    """
    paths = glob.glob(sensor_glob)
    if not paths:
        raise RuntimeError("DS18B20 not found under /sys/bus/w1/devices/28-*/w1_slave")

    with open(paths[0], "r", encoding="utf-8") as f:
        lines = f.read().strip().splitlines()

    if len(lines) < 2 or not lines[0].strip().endswith("YES"):
        raise RuntimeError("DS18B20 CRC invalid (first line does not end with YES)")

    marker = "t="
    if marker not in lines[1]:
        raise RuntimeError("DS18B20 temperature token 't=' not found")

    milli_c = int(lines[1].split(marker, 1)[1])
    return milli_c / 1000.0


def _apply_heater_duties(channels, base, max_duty, lower_active=True):
    for ch in channels:
        if ch["pin"] == LOWER_HEATER_PIN and not lower_active:
            level = 0.0
        else:
            level = max(0.0, min(float(max_duty), float(base) * ch["scale"]))
        ch["pwm"].ChangeDutyCycle(level)
        ch["duty"] = level


def _set_heaters_duty_smooth(
    channels, current_base, target_base, max_duty, ramp_step, ramp_delay, lower_active=True
):
    """Ramp PID base duty; each heater gets base * its scale (capped at max_duty)."""
    target_base = max(0.0, min(float(max_duty), float(target_base)))
    base = float(current_base)
    if abs(target_base - base) < 0.001:
        _apply_heater_duties(channels, base, max_duty, lower_active)
        return base

    direction = 1.0 if target_base > base else -1.0
    step = abs(float(ramp_step)) * direction
    while (direction > 0 and base < target_base) or (direction < 0 and base > target_base):
        base += step
        if direction > 0 and base > target_base:
            base = target_base
        if direction < 0 and base < target_base:
            base = target_base
        _apply_heater_duties(channels, base, max_duty, lower_active)
        time.sleep(float(ramp_delay))
    return base


def _start_heater_channels(heater_pins, pwm_freq, duty_scale=None):
    duty_scale = duty_scale or HEATER_DUTY_SCALE
    GPIO.setmode(GPIO.BCM)
    channels = []
    for pin in heater_pins:
        pin = int(pin)
        GPIO.setup(pin, GPIO.OUT)
        pwm = GPIO.PWM(pin, int(pwm_freq))
        pwm.start(0)
        channels.append(
            {
                "pin": pin,
                "pwm": pwm,
                "scale": float(duty_scale.get(pin, 1.0)),
                "duty": 0.0,
            }
        )
    return channels


def _stop_heater_channels_all(channels):
    _stop_heater_channels(channels)


def _format_heater_duties(channels):
    return ", ".join(f"GPIO{ch['pin']}={ch['duty']:.1f}%" for ch in channels)


def Start_incubation(
    target_temp_c,
    duration_minutes,
    poll_seconds=2.0,
    on_tick=None,
    heater_pins=None,
    pwm_pin=None,
    heater_duty_scale=None,
    pwm_freq=100,
    kp=10.0,
    ki=0.2,
    kd=2.0,
    max_duty=20.0,
    ramp_step=2.0,
    ramp_delay=0.1,
    lower_off_remaining_min=None,
    lower_off_below_target_c=None,
    pre_imaging_cool_down_min=None,
    keep_upper_heater_on_exit=False,
):
    """
    Maintain incubation temperature using PID + one or more BTS PWM heater outputs.

    Both heaters use the same DS18B20 reading and PID output. The upper heater
    (GPIO 26 / pin 37) receives 30% more duty than the lower (GPIO 12 / pin 32).

    Lower heater is switched off (upper only) when temperature reaches
    ``target - lower_off_below_target_c`` (default 3 °C), to reduce lid vapour.

    Before imaging, both heaters turn off for a cool-down so dishes match ambient
    and condensation is reduced:
    - holds longer than the cool-down: last N minutes both off (within the hold);
    - shorter holds: heat for the full duration, then add N minutes with heaters off.

    If ``keep_upper_heater_on_exit`` is True, the upper heater stays on at the
    last PID duty after incubation. Prefer leaving this False when imaging follows
    so dishes can cool. Call ``release_incubation_heaters()`` when heating should stop.

    Args:
        target_temp_c: target temperature in Celsius.
        duration_minutes: how long to maintain incubation.
        heater_pins: BCM pin tuple for BTS PWM inputs (default lower + upper).
        pwm_pin: legacy single-pin alias; ignored when heater_pins is set.
        heater_duty_scale: optional dict {bcm_pin: multiplier} overriding defaults.
        pwm_freq: PWM frequency in Hz.
        kp, ki, kd: PID gains.
        max_duty: safety cap per heater duty cycle (%).
        ramp_step/ramp_delay: soft-ramp behavior to reduce thermal overshoot.
        poll_seconds: sensor polling interval.
        lower_off_remaining_min: legacy alias for ``pre_imaging_cool_down_min``.
        lower_off_below_target_c: turn lower off once temp >= target minus this
            (default 3). Set 0 or less to disable the temperature cutoff.
        pre_imaging_cool_down_min: both heaters off for this many minutes before
            return / imaging (default 5).
        keep_upper_heater_on_exit: keep upper heater PWM on after incubation ends.
        on_tick: optional callback(elapsed_s, remaining_s, temp_c, target_temp_c).
    """
    global _held_upper_channels
    release_incubation_heaters()
    target_temp_c = float(target_temp_c)
    duration_s = max(0.0, float(duration_minutes) * 60.0)
    poll_seconds = max(0.2, float(poll_seconds))
    max_duty = max(1.0, min(100.0, float(max_duty)))
    if pre_imaging_cool_down_min is None:
        if lower_off_remaining_min is not None:
            pre_imaging_cool_down_min = lower_off_remaining_min
        else:
            pre_imaging_cool_down_min = PRE_IMAGING_COOL_DOWN_MIN
    cool_down_s = max(0.0, float(pre_imaging_cool_down_min) * 60.0)
    # Long holds: cool inside the scheduled window. Short holds: heat fully, then add cool.
    if duration_s > cool_down_s > 0:
        heat_duration_s = duration_s - cool_down_s
        append_cool_down = False
    else:
        heat_duration_s = duration_s
        append_cool_down = cool_down_s > 0
    if lower_off_below_target_c is None:
        lower_off_below_target_c = LOWER_HEATER_OFF_BELOW_TARGET_C
    lower_off_below_target_c = float(lower_off_below_target_c)
    use_temp_cutoff = lower_off_below_target_c > 0
    lower_off_threshold_c = target_temp_c - lower_off_below_target_c

    if heater_pins is None:
        heater_pins = (int(pwm_pin),) if pwm_pin is not None else DEFAULT_HEATER_PINS
    heater_pins = tuple(int(p) for p in heater_pins)
    if not heater_pins:
        raise ValueError("At least one heater pin is required")

    scale_map = dict(HEATER_DUTY_SCALE)
    if heater_duty_scale:
        scale_map.update({int(k): float(v) for k, v in heater_duty_scale.items()})

    print(
        f"[Incubation] Start PID: target={target_temp_c:.2f}C, duration={duration_minutes} min"
    )
    scale_desc = ", ".join(
        f"GPIO{p}×{scale_map.get(p, 1.0):g}" for p in heater_pins
    )
    cool_desc = (
        f"both heaters OFF last {pre_imaging_cool_down_min:g} min (cool before imaging)"
        if duration_s > cool_down_s > 0
        else (
            f"heat full hold, then {pre_imaging_cool_down_min:g} min cool-down "
            f"(both heaters OFF) before imaging"
            if cool_down_s > 0
            else "no pre-imaging cool-down"
        )
    )
    cutoff_desc = (
        f"lower off at temp>={lower_off_threshold_c:.1f}C "
        f"(target-{lower_off_below_target_c:g}); {cool_desc}"
        if use_temp_cutoff
        else cool_desc
    )
    print(
        f"[Incubation] Heater PWM pins={heater_pins}, duty scale: {scale_desc}, "
        f"freq={int(pwm_freq)}Hz, PID(Kp={kp}, Ki={ki}, Kd={kd}), max_duty={max_duty:.1f}%, "
        f"{cutoff_desc}"
    )

    heater_channels = _start_heater_channels(heater_pins, pwm_freq, scale_map)

    pid = None
    i_term = 0.0
    prev_error = 0.0
    current_duty = 0.0
    cool_logged = False
    lower_off_near_target = False
    if PID is not None:
        pid = PID(float(kp), float(ki), float(kd), setpoint=target_temp_c)
        pid.output_limits = (0.0, max_duty)
        try:
            pid.sample_time = float(poll_seconds)
        except Exception:
            pass

    start = time.time()
    if duration_s > cool_down_s > 0:
        total_planned_s = duration_s
    elif append_cool_down:
        total_planned_s = heat_duration_s + cool_down_s
    else:
        total_planned_s = heat_duration_s

    def _notify_tick(temp_c):
        if on_tick is None:
            return
        elapsed = time.time() - start
        remaining = max(0.0, total_planned_s - elapsed)
        try:
            on_tick(elapsed, remaining, temp_c, target_temp_c)
        except Exception:
            pass

    def _force_heaters_off():
        nonlocal current_duty
        current_duty = _set_heaters_duty_smooth(
            heater_channels,
            current_base=current_duty,
            target_base=0.0,
            max_duty=max_duty,
            ramp_step=ramp_step,
            ramp_delay=ramp_delay,
            lower_active=False,
        )
        _apply_heater_duties(heater_channels, 0.0, max_duty, lower_active=False)

    def _run_cool_down(seconds):
        nonlocal cool_logged
        if seconds <= 0:
            return
        if not cool_logged:
            print(
                f"[Incubation] Pre-imaging cool-down {seconds / 60.0:g} min — "
                "both heaters OFF so dishes cool (reduce condensation)"
            )
            cool_logged = True
        _force_heaters_off()
        cool_start = time.time()
        while (time.time() - cool_start) < seconds:
            try:
                temp_c = _read_ds18b20_c()
            except RuntimeError as exc:
                print(f"[Incubation] Cool-down sensor read failed: {exc}")
                temp_c = float("nan")
            print(
                f"[Incubation] cool {temp_c:.2f}C -> heaters OFF "
                f"({_format_heater_duties(heater_channels)})"
            )
            _notify_tick(temp_c)
            time.sleep(poll_seconds)
        _force_heaters_off()

    try:
        try:
            _notify_tick(_read_ds18b20_c())
        except RuntimeError as exc:
            print(f"[Incubation] Initial sensor read failed: {exc}")
            _notify_tick(float("nan"))

        heat_start = time.time()
        while (time.time() - heat_start) < heat_duration_s:
            temp_c = _read_ds18b20_c()
            if use_temp_cutoff and (lower_off_near_target or temp_c >= lower_off_threshold_c):
                if not lower_off_near_target:
                    print(
                        f"[Incubation] {temp_c:.2f}C >= {lower_off_threshold_c:.2f}C "
                        f"(target {target_temp_c:.1f}C - {lower_off_below_target_c:g}) — "
                        "lower heater OFF, upper only to reduce lid vapour"
                    )
                    lower_off_near_target = True
                lower_active = False
            else:
                lower_active = True

            if pid is not None:
                requested_duty = float(pid(temp_c))
            else:
                error = target_temp_c - temp_c
                i_term += error * poll_seconds
                d_term = (error - prev_error) / poll_seconds
                prev_error = error
                raw = (float(kp) * error) + (float(ki) * i_term) + (float(kd) * d_term)
                requested_duty = max(0.0, min(max_duty, raw))

            current_duty = _set_heaters_duty_smooth(
                heater_channels,
                current_base=current_duty,
                target_base=requested_duty,
                max_duty=max_duty,
                ramp_step=ramp_step,
                ramp_delay=ramp_delay,
                lower_active=lower_active,
            )
            print(
                f"[Incubation] {temp_c:.2f}C -> base {current_duty:.1f}% "
                f"({_format_heater_duties(heater_channels)})"
            )
            _notify_tick(temp_c)
            time.sleep(poll_seconds)

        # Cool-down: both heaters off before imaging / return.
        if duration_s > cool_down_s > 0:
            _run_cool_down(cool_down_s)
        elif append_cool_down:
            _run_cool_down(cool_down_s)
    finally:
        global _held_upper_channels
        if keep_upper_heater_on_exit:
            _stop_heater_channels(heater_channels, pins_to_stop={LOWER_HEATER_PIN})
            upper_ch = next(
                (ch for ch in heater_channels if ch["pin"] == UPPER_HEATER_PIN), None
            )
            if upper_ch and upper_ch["duty"] > 0:
                _held_upper_channels = [upper_ch]
                print(
                    f"[Incubation] Completed. Upper heater held ON at "
                    f"{upper_ch['duty']:.1f}% for imaging."
                )
            else:
                _stop_heater_channels_all(heater_channels)
                print("[Incubation] Completed. All heaters OFF.")
        else:
            _stop_heater_channels_all(heater_channels)
            print("[Incubation] Completed. All heaters OFF.")


def keep_temperature_pid(temperature_to_keep_c, minutes, **kwargs):
    """
    Convenience wrapper for main usage.

    Example:
        keep_temperature_pid(37.0, 60)  # keep 37C for 60 minutes
    """
    return Start_incubation(temperature_to_keep_c, minutes, **kwargs)


def _test_single_heater(
    pin,
    label,
    duty_percent,
    duration_minutes,
    pwm_freq,
    on_tick=None,
    poll_seconds=2.0,
):
    """Run one heater at a fixed duty for a self-test; the other stays off."""
    global _heater_test_stop, _test_heater_channels

    duty = max(0.0, min(100.0, float(duty_percent)))
    duration_s = max(0.0, float(duration_minutes) * 60.0)
    poll_seconds = max(0.2, float(poll_seconds))
    pin = int(pin)

    stop_heater_test()
    release_incubation_heaters()
    _heater_test_stop = False

    print(
        f"[Incubation] {label} heater TEST: {duty:.0f}% for {duration_minutes:g} min "
        f"(GPIO {pin})"
    )
    channels = _start_heater_channels((pin,), int(pwm_freq), {pin: 1.0})
    _test_heater_channels = channels
    start = time.time()

    try:
        for ch in channels:
            ch["pwm"].ChangeDutyCycle(duty)
            ch["duty"] = duty
        while (time.time() - start) < duration_s:
            if _heater_test_stop:
                print(f"[Incubation] {label} heater TEST aborted.")
                break
            elapsed = time.time() - start
            remaining = max(0.0, duration_s - elapsed)
            try:
                temp_c = _read_ds18b20_c()
            except RuntimeError:
                temp_c = float("nan")
            print(
                f"[Incubation] TEST {temp_c:.2f}C -> {label.lower()} {duty:.0f}% "
                f"({remaining / 60.0:.1f} min left)"
            )
            if on_tick is not None:
                try:
                    on_tick(elapsed, remaining, temp_c, float("nan"))
                except Exception:
                    pass
            time.sleep(poll_seconds)
    finally:
        for ch in list(channels):
            _stop_channel(ch)
        if _test_heater_channels is channels:
            _test_heater_channels = []
        print(f"[Incubation] {label} heater TEST complete — OFF.")


def test_upper_heater(
    duty_percent=None,
    duration_minutes=None,
    pwm_freq=None,
    on_tick=None,
    poll_seconds=2.0,
):
    """
    Switch on the upper heater only at a fixed duty for a short self-test.

    Default: 50% for 5 minutes. Lower heater stays off. Call ``stop_heater_test()``
    or ``release_incubation_heaters()`` to abort early (e.g. GUI Close).
    """
    if duty_percent is None:
        duty_percent = UPPER_HEATER_TEST_DUTY
    if duration_minutes is None:
        duration_minutes = UPPER_HEATER_TEST_MINUTES
    if pwm_freq is None:
        pwm_freq = UPPER_HEATER_TEST_PWM_FREQ
    return _test_single_heater(
        UPPER_HEATER_PIN,
        "Upper",
        duty_percent,
        duration_minutes,
        pwm_freq,
        on_tick=on_tick,
        poll_seconds=poll_seconds,
    )


def test_lower_heater(
    duty_percent=None,
    duration_minutes=None,
    pwm_freq=None,
    on_tick=None,
    poll_seconds=2.0,
):
    """
    Switch on the lower heater only at a fixed duty for a short self-test.

    Default: 50% for 5 minutes. Upper heater stays off. Call ``stop_heater_test()``
    or ``release_incubation_heaters()`` to abort early (e.g. GUI Close).
    """
    if duty_percent is None:
        duty_percent = LOWER_HEATER_TEST_DUTY
    if duration_minutes is None:
        duration_minutes = LOWER_HEATER_TEST_MINUTES
    if pwm_freq is None:
        pwm_freq = LOWER_HEATER_TEST_PWM_FREQ
    return _test_single_heater(
        LOWER_HEATER_PIN,
        "Lower",
        duty_percent,
        duration_minutes,
        pwm_freq,
        on_tick=on_tick,
        poll_seconds=poll_seconds,
    )


