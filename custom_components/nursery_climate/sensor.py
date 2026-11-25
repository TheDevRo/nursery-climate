from homeassistant.components.sensor import SensorDeviceClass, SensorEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([Status(entry)])


class Status(SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Mode"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["off", "waiting", "sensor_lost", "cooling", "heating", "in_band"]
    _attr_should_poll = False

    def __init__(self, entry):
        self.ctl = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_mode"
        self._attr_device_info = self.ctl.device

    @property
    def native_value(self):
        return self.ctl.status

    @property
    def extra_state_attributes(self):
        return {
            "setpoint": self.ctl.target,
            "rate_per_min": round(self.ctl.rate, 3),
            "room_temp": self.ctl.room,
            "reading_age_min": round(self.ctl.reading_age, 1),
        }

    async def async_added_to_hass(self):
        self.ctl.listeners.append(self.async_write_ha_state)
        self.async_on_remove(lambda: self.ctl.listeners.remove(self.async_write_ha_state))
