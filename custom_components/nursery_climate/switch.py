from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.restore_state import RestoreEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([Control(entry)])


class Control(SwitchEntity, RestoreEntity):
    """On = steer the thermostat. Off = hand it back at the resting setpoint."""

    _attr_has_entity_name = True
    _attr_name = "Control"
    _attr_icon = "mdi:thermostat-auto"

    def __init__(self, entry):
        self.ctl = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_control"
        self._attr_device_info = self.ctl.device

    @property
    def is_on(self):
        return self.ctl.enabled

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        # Restore without touching the thermostat; the next sensor change resumes control.
        self.ctl.enabled = bool(last and last.state == "on")
        self.ctl.listeners.append(self.async_write_ha_state)  # schedule flips it too
        self.async_on_remove(lambda: self.ctl.listeners.remove(self.async_write_ha_state))

    async def async_turn_on(self, **kwargs):
        await self.ctl.set_enabled(True)

    async def async_turn_off(self, **kwargs):
        await self.ctl.set_enabled(False)
