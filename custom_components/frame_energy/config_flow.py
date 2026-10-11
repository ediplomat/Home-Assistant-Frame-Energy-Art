"""Local-only configuration; no credentials needed."""
from pathlib import Path
import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, DEFAULTS

class FrameEnergyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors = {}
        if user_input is not None:
            config = {**DEFAULTS, **user_input}
            exists = await self.hass.async_add_executor_job(Path(config["background_path"]).is_file)
            if not exists:
                errors["background_path"] = "missing_background"
            elif config["background_path"] == config["output_path"]:
                errors["output_path"] = "same_path"
            else:
                return self.async_create_entry(title="Frame Energy Art", data=config)
        schema = vol.Schema({vol.Required(key, default=value): str for key, value in DEFAULTS.items()})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
