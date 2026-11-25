from homeassistant.components.select import SelectEntity
from homeassistant.helpers.restore_state import RestoreEntity

from . import HAND_BACK_MODES


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([HandBackMode(entry)])


class HandBackMode(SelectEntity, RestoreEntity):
    """Thermostat mode when control turns off. auto = heat or cool toward the hand-back setpoint."""

    _attr_has_entity_name = True
    _attr_name = "Hand-back mode"
    _attr_icon = "mdi:thermostat"
    _attr_options = HAND_BACK_MODES

    def __init__(self, entry):
        self.ctl = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_hand_back_mode"
        self._attr_device_info = self.ctl.device

    @property
    def current_option(self):
        return self.ctl.hand_back_mode

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state in HAND_BACK_MODES:
            self.ctl.hand_back_mode = last.state

    async def async_select_option(self, option: str) -> None:
        self.ctl.hand_back_mode = option
        self.async_write_ha_state()
