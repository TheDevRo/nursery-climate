"""Pure control math. No Home Assistant imports so it can be tested with plain python."""

WINDOW = 300  # seconds of history for the rate, same as the old derivative helper
MIN_SET, MAX_SET = 55, 85  # ponytail: °F only, matches the old automation; derive from unit system if shared
DEADBAND = 1.0  # °F; "auto" hand-back keeps a heat/cool mode when the house is this close to the target


def slope(samples, now):
    """°F/min across the samples inside WINDOW. 0 when there is under 30 s of data."""
    pts = [(t, v) for t, v in samples if t >= now - WINDOW]
    if len(pts) < 2 or pts[-1][0] - pts[0][0] < 30:
        return 0.0
    return (pts[-1][1] - pts[0][1]) / ((pts[-1][0] - pts[0][0]) / 60)


def accept(new, last, pending, max_jump):
    """Spike filter. Return (use_it, pending).

    A reading more than max_jump from the last good one is held back. It is used once a second
    reading lands near it (the room really changed); a reading back near the old value drops it.
    max_jump 0 or no previous reading = accept everything.
    """
    if last is None or not max_jump or abs(new - last) <= max_jump:
        return True, None
    if pending is not None and abs(new - pending) <= max_jump:
        return True, None
    return False, new


def decide(room, ref, low, high, kp, kd, rate):
    """Return (hvac_mode or None, setpoint, status).

    setpoint = ref - kp*(room - mid) - kd*rate, clamped. The mode only flips at the band edges;
    inside the band the setpoint alone moves, so the HVAC eases off before it overshoots.
    """
    raw = ref - kp * (room - (low + high) / 2) - kd * rate
    target = round(min(max(raw, MIN_SET), MAX_SET), 1)
    if room > high:
        return "cool", target, "cooling"
    if room < low:
        return "heat", target, "heating"
    return None, target, "in_band"


def hand_back(choice, house, target, current):
    """Return the hvac mode to hand the thermostat back in, or None to leave its mode alone.

    A thermostat that is already off (or unreachable) stays as it is. "auto" heats when the
    house is below the target and cools when it is above. Within DEADBAND it keeps a heat or
    cool mode, so a degree of drift doesn't flip the HVAC.
    """
    if current in (None, "off", "unavailable", "unknown"):
        return None
    if choice != "auto":
        return choice
    if house is None:
        return None
    if current in ("heat", "cool") and abs(house - target) <= DEADBAND:
        return current
    return "cool" if house > target else "heat"
