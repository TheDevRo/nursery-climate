from homeassistant.components.number import NumberMode, RestoreNumber

from . import NUMBERS


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(Setting(entry, key) for key in NUMBERS)


class Setting(RestoreNumber):
    _attr_has_entity_name = True

    def __init__(self, entry, key):
        self.ctl = entry.runtime_data
        self.key = key
        name, _, lo, hi, step, unit = NUMBERS[key]
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = self.ctl.device
        self._attr_native_min_value = lo
        self._attr_native_max_value = hi
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._attr_mode = NumberMode.BOX if unit else NumberMode.SLIDER

    @property
    def native_value(self):
        return self.ctl.values[self.key]

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last and last.native_value is not None:
            self.ctl.values[self.key] = last.native_value

    async def async_set_native_value(self, value):
        self.ctl.values[self.key] = value
        self.async_write_ha_state()
        await self.ctl.run()
