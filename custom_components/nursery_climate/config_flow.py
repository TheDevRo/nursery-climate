import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_NAME
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig

from . import DOMAIN

ENTITIES = {
    vol.Required("sensor"): EntitySelector(
        EntitySelectorConfig(domain="sensor", device_class="temperature")
    ),
    vol.Required("climate"): EntitySelector(EntitySelectorConfig(domain="climate")),
}
SCHEMA = vol.Schema({vol.Required(CONF_NAME, default="Kids Room"): str, **ENTITIES})


class NurseryClimateFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            await self.async_set_unique_id(user_input["sensor"])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)
        return self.async_show_form(step_id="user", data_schema=SCHEMA)

    async def async_step_reconfigure(self, user_input=None):
        """Swap the sensor or thermostat. Settings survive: entities restore their last values."""
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            if user_input["sensor"] != entry.unique_id:
                await self.async_set_unique_id(user_input["sensor"])
                self._abort_if_unique_id_configured()
            return self.async_update_reload_and_abort(
                entry, unique_id=user_input["sensor"], data_updates=user_input
            )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(vol.Schema(ENTITIES), entry.data),
        )
