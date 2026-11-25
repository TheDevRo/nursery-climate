"""Nursery Climate: steer a thermostat so a room with its own temperature sensor stays in a band."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import time as dtime, timedelta
from time import monotonic

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .logic import WINDOW, accept, decide, hand_back, slope

DOMAIN = "nursery_climate"
PLATFORMS = [Platform.NUMBER, Platform.SELECT, Platform.SENSOR, Platform.SWITCH, Platform.TIME]
_LOGGER = logging.getLogger(__name__)
SANE = (40, 85)  # °F; readings outside this are treated as no reading

# key: (name, default, min, max, step, unit)
NUMBERS = {
    "low": ("Low", 67.0, 60, 78, 0.5, "°F"),
    "high": ("High", 70.5, 62, 80, 0.5, "°F"),
    "kp": ("Kp", 2.5, 0, 6, 0.1, None),
    "kd": ("Kd", 8.0, 0, 20, 0.5, None),
    "rest": ("Resting setpoint", 69.0, 55, 85, 0.5, "°F"),  # lost-sensor failsafe
    "handback": ("Hand-back setpoint", 69.0, 55, 85, 0.5, "°F"),  # when control turns off
    # 0 turns either safeguard off
    "timeout": ("Sensor timeout", 20.0, 0, 240, 1, "min"),
    "max_jump": ("Max jump", 3.0, 0, 10, 0.5, "°F"),
}
# key: (name, default). Control turns on at start and off at end; start == end means no schedule.
TIMES = {"start": ("Schedule start", dtime(19)), "end": ("Schedule end", dtime(7))}
# Thermostat mode when control turns off. "auto" = heat or cool toward the hand-back setpoint.
HAND_BACK_MODES = ["auto", "heat", "cool", "off"]


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None  # unknown / unavailable / missing


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ctl = entry.runtime_data = Controller(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    ctl.reading(hass.states.get(ctl.sensor))  # after numbers restore, so max_jump is known
    entry.async_on_unload(
        async_track_state_change_event(hass, [ctl.sensor, ctl.climate], ctl.on_change)
    )
    # A dead sensor sends no events, so the timeout needs its own clock.
    entry.async_on_unload(async_track_time_interval(hass, ctl.tick, timedelta(minutes=1)))
    entry.async_on_unload(ctl.unschedule)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


class Controller:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.sensor = entry.data["sensor"]
        self.climate = entry.data["climate"]
        self.values = {k: v[1] for k, v in NUMBERS.items()}
        self.times = {k: v[1] for k, v in TIMES.items()}
        self.hand_back_mode = "auto"
        self.enabled = False
        self.status = "off"
        self.target: float | None = None
        self.rate = 0.0
        self.room: float | None = None  # last accepted reading
        self.room_at = monotonic()  # when it was taken (setup time until the first one)
        self._pending: float | None = None  # a big jump waiting for a second reading
        self.samples: deque[tuple[float, float]] = deque()
        self.listeners: list = []  # entities' async_write_ha_state
        self.device = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=entry.title)
        self._unsubs: list = []
        self._lock = asyncio.Lock()

    def notify(self) -> None:
        for write in self.listeners:
            write()

    @callback
    def unschedule(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []

    @callback
    def schedule(self) -> None:
        self.unschedule()
        start, end = self.times["start"], self.times["end"]
        if start == end:
            return
        for at, fn in ((start, self._at_start), (end, self._at_end)):
            self._unsubs.append(
                async_track_time_change(self.hass, fn, hour=at.hour, minute=at.minute, second=at.second)
            )

    async def _at_start(self, now) -> None:
        await self.set_enabled(True)

    async def _at_end(self, now) -> None:
        await self.set_enabled(False)

    async def tick(self, now) -> None:
        await self.run()

    @callback
    def reading(self, st: State | None) -> None:
        """Take a sensor state. Missing, insane and unconfirmed spike values are dropped."""
        t = _num(st.state if st else None)
        if t is None or not SANE[0] < t < SANE[1]:
            return
        ok, self._pending = accept(t, self.room, self._pending, self.values["max_jump"])
        if not ok:
            _LOGGER.info("%s: holding back jump %s -> %s until confirmed", self.sensor, self.room, t)
            return
        now = monotonic()
        self.room, self.room_at = t, now
        self.samples.append((now, t))
        while self.samples[0][0] < now - WINDOW:
            self.samples.popleft()

    @callback
    def on_change(self, event: Event[EventStateChangedData]) -> None:
        if event.data["entity_id"] == self.sensor:
            self.reading(event.data["new_state"])
        self.hass.async_create_task(self.run())

    @property
    def reading_age(self) -> float:
        """Minutes since the last accepted reading."""
        return (monotonic() - self.room_at) / 60

    async def run(self) -> None:
        async with self._lock:
            try:
                await self._step()
            except HomeAssistantError as err:
                _LOGGER.warning("Could not command %s: %s", self.climate, err)
        self.notify()

    async def _step(self) -> None:
        if not self.enabled:
            self.status = "off"
            return

        # A sensor re-reporting the same value fires no event; count it as fresh.
        st = self.hass.states.get(self.sensor)
        if st and self.room is not None and _num(st.state) == self.room:
            age = (dt_util.utcnow() - st.last_reported).total_seconds()
            self.room_at = max(self.room_at, monotonic() - age)

        timeout = self.values["timeout"]
        if timeout and self.reading_age > timeout:
            if self.status != "sensor_lost":
                _LOGGER.warning("%s: no good reading for %d min, resting thermostat", self.sensor, timeout)
            self.status = "sensor_lost"
            self.target = self.values["rest"]
            await self._hold(self.values["rest"])
            return

        cs: State | None = self.hass.states.get(self.climate)
        ref = _num(cs.attributes.get("current_temperature")) if cs else None
        if self.room is None or ref is None or not SANE[0] < ref < SANE[1]:
            self.status = "waiting"
            return

        v = self.values
        self.rate = slope(self.samples, monotonic())
        mode, self.target, self.status = decide(
            self.room, ref, v["low"], v["high"], v["kp"], v["kd"], self.rate
        )
        cur_mode = cs.state
        if mode and cur_mode != mode:
            await self._call("set_hvac_mode", hvac_mode=mode)
            cur_mode = mode
        cur_set = _num(cs.attributes.get("temperature"))
        if cur_mode in ("heat", "cool") and (cur_set is None or abs(self.target - cur_set) >= 0.5):
            await self._call("set_temperature", temperature=self.target)

    async def _hold(self, temp: float, mode: str | None = None) -> None:
        """Set the thermostat to temp. Without a mode it keeps its current one."""
        cs = self.hass.states.get(self.climate)
        if not cs:
            return
        a = cs.attributes
        changed = mode is not None and mode != cs.state
        if changed:
            await self._call("set_hvac_mode", hvac_mode=mode)
        mode = mode or cs.state
        if mode in ("heat", "cool"):
            cur = _num(a.get("temperature"))
            if changed or cur is None or abs(cur - temp) >= 0.5:
                await self._call("set_temperature", temperature=temp)
        elif mode == "heat_cool":
            if changed or (_num(a.get("target_temp_low")), _num(a.get("target_temp_high"))) != (temp - 1, temp + 1):
                await self._call("set_temperature", target_temp_low=temp - 1, target_temp_high=temp + 1)

    async def _hand_back(self) -> None:
        """Control is off: put the thermostat in the hand-back mode at the hand-back setpoint."""
        cs = self.hass.states.get(self.climate)
        if not cs:
            return
        house = _num(cs.attributes.get("current_temperature"))
        if house is not None and not SANE[0] < house < SANE[1]:
            house = None
        target = self.values["handback"]
        mode = hand_back(self.hand_back_mode, house, target, cs.state)
        _LOGGER.info("Handing %s back: house %s, mode %s, setpoint %s", self.climate, house, mode or cs.state, target)
        await self._hold(target, mode)

    async def set_enabled(self, on: bool) -> None:
        self.enabled = on
        self.notify()  # switch shows the new state before the slow thermostat call
        if on:
            await self.run()
            return
        async with self._lock:
            try:
                await self._hand_back()
            except HomeAssistantError as err:
                _LOGGER.warning("Could not reset %s: %s", self.climate, err)
            self.status = "off"
        self.notify()

    async def _call(self, service: str, **data) -> None:
        await self.hass.services.async_call(
            "climate", service, {"entity_id": self.climate, **data}, blocking=True
        )
