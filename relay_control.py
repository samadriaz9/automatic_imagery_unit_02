import time
import smbus

# Second PCF8574 used for relays (cascaded board)
# First board is typically at 0x20; second at 0x21.
RELAY_PCF8574_ADDRESS = 0x20

# Convenience channel constants (PCF8574 pins)
P0 = 0
P1 = 1
P2 = 2
P3 = 3
P4 = 4
P5 = 5
P6 = 6
P7 = 7

# Only these channels are used as relays in current wiring.
RELAY_CHANNELS = (P1, P7)

# Convenience relay-number aliases (many relay boards label relays as 1..8)
RELAY1 = 0
RELAY2 = 1
RELAY3 = 2
RELAY4 = 3
RELAY5 = 4
RELAY6 = 5
RELAY7 = 6
RELAY8 = 7

# PCF8574 + relay boards are usually ACTIVE-LOW:
# - Writing bit = 1 -> relay OFF
# - Writing bit = 0 -> relay ON

_bus = None
_initialized = False
_state = 0xFF  # all relays OFF (all bits high)


def _ensure_i2c():
    """Initialize I2C bus for the relay PCF8574 (once)."""
    global _bus, _initialized, _state
    if not _initialized:
        _bus = smbus.SMBus(1)
        # Start with all outputs HIGH (relays off)
        _state = 0xFF
        _bus.write_byte(RELAY_PCF8574_ADDRESS, _state)
        _initialized = True


def _write_state():
    """Write current state byte to the relay PCF8574."""
    _ensure_i2c()
    _bus.write_byte(RELAY_PCF8574_ADDRESS, _state)


def set_relay(channel: int, on: bool):
    """
    Turn a single relay ON or OFF.

    channel: 0–7 correspond to P0–P7 on the second PCF8574.
    on=True  -> relay ON  (bit driven LOW)
    on=False -> relay OFF (bit driven HIGH)
    """
    global _state
    if channel not in RELAY_CHANNELS:
        raise ValueError(f"channel must be one of {RELAY_CHANNELS}")

    mask = 1 << channel
    if on:
        # Active-low: clear bit to drive pin low -> relay ON
        _state &= ~mask
    else:
        # Set bit to 1 -> pin high -> relay OFF
        _state |= mask

    _write_state()


def run_relay_sequence():
    """
    Run only relay channels (P6, P7) ON for 2 seconds, one after another.
    """
    _ensure_i2c()
    for ch in RELAY_CHANNELS:
        print(f"Relay on P{ch}: ON")
        set_relay(ch, True)
        time.sleep(2)
        print(f"Relay on P{ch}: OFF")
        set_relay(ch, False)
        time.sleep(0.2)


def run_relay(channel: int, seconds: float):
    """
    Turn one relay ON for `seconds`, then OFF.

    Example:
        run_relay(P1, 2)
    """
    if seconds < 0:
        raise ValueError("seconds must be >= 0")

    # Ensure bus is initialized in exactly the same way
    # as the working run_relay_sequence().
    _ensure_i2c()

    print(f"run_relay(): Relay on P{channel}: ON for {seconds}s")
    set_relay(channel, True)
    time.sleep(seconds)
    print(f"run_relay(): Relay on P{channel}: OFF")
    set_relay(channel, False)


def cleanup():
    """Turn all relays off and close the I2C bus."""
    global _bus, _initialized, _state
    if _initialized and _bus is not None:
        try:
            # All OFF
            _state = 0xFF
            _bus.write_byte(RELAY_PCF8574_ADDRESS, _state)
        except Exception:
            pass
        try:
            _bus.close()
        except AttributeError:
            pass
    _bus = None
    _initialized = False

