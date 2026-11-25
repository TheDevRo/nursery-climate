from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.helpers.restore_state import RestoreEntity

from . import TIMES


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(ScheduleTime(entry, key) for key in TIMES)


class ScheduleTime(TimeEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:clock-outline"

    def __init__(self, entry, key):
        self.ctl = entry.runtime_data
        self.key = key
        self._attr_name = TIMES[key][0]
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = self.ctl.device

    @property
    def native_value(self):
        return self.ctl.times[self.key]

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last:
            try:
                self.ctl.times[self.key] = time.fromisoformat(last.state)
            except ValueError:
                pass  # unknown/unavailable: keep the default
        self.ctl.schedule()

    async def async_set_value(self, value: time) -> None:
        self.ctl.times[self.key] = value
        self.ctl.schedule()
        self.async_write_ha_state()
