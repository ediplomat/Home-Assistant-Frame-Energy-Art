"""Local-only configuration; the TV token comes from on-screen pairing."""
import logging
from pathlib import Path

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig, SelectSelectorMode

from . import tv
from .const import (CONF_SHOW_UPDATE_TIME, CONF_TV_HOST, CONF_TV_TOKEN, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL,
                    DEFAULTS, DOMAIN, OPTIONAL_KEYS, UPDATE_INTERVALS)
from .render import LABEL_DEFAULTS

_LOGGER = logging.getLogger(__name__)


def _schema(current: dict) -> vol.Schema:
    fields = {}
    for key, value in DEFAULTS.items():
        if key in OPTIONAL_KEYS:
            # Optional with a suggested value (not a default), so the field can be cleared.
            fields[vol.Optional(key, description={"suggested_value": current.get(key, value)})] = str
        else:
            fields[vol.Required(key, default=current.get(key, value))] = str
    for key, value in LABEL_DEFAULTS.items():
        fields[vol.Optional(key, default=current.get(key, value))] = str
    fields[vol.Optional(CONF_SHOW_UPDATE_TIME, default=bool(current.get(CONF_SHOW_UPDATE_TIME, False)))] = bool
    fields[vol.Required(CONF_UPDATE_INTERVAL, default=str(current.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)))] = \
        SelectSelector(SelectSelectorConfig(options=list(UPDATE_INTERVALS), mode=SelectSelectorMode.DROPDOWN,
                                            translation_key=CONF_UPDATE_INTERVAL))
    fields[vol.Required(CONF_TV_HOST, default=current.get(CONF_TV_HOST, ""))] = str
    return vol.Schema(fields)


def _with_optional(user_input: dict) -> dict:
    """A cleared optional field is missing from the form result: store it as empty."""
    return {**user_input, **{key: user_input.get(key, "").strip() for key in OPTIONAL_KEYS}}


async def _validate(hass, config: dict) -> dict:
    errors = {}
    background = config.get("background_path", "")
    if not background:
        return errors  # the built-in painting
    exists = await hass.async_add_executor_job(Path(background).is_file)
    if not exists:
        errors["background_path"] = "missing_background"
    elif background == config["output_path"]:
        errors["output_path"] = "same_path"
    return errors


class FrameEnergyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._config = {}

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors = {}
        if user_input is not None:
            config = {**DEFAULTS, **_with_optional(user_input)}
            config[CONF_TV_HOST] = config.get(CONF_TV_HOST, "").strip()
            errors = await _validate(self.hass, config)
            if not config[CONF_TV_HOST]:
                errors[CONF_TV_HOST] = "missing_host"
            if not errors:
                self._config = config
                return await self.async_step_pair()
        return self.async_show_form(step_id="user", data_schema=_schema(_with_optional(user_input) if user_input else {}), errors=errors)

    async def async_step_pair(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                token = await self.hass.async_add_executor_job(tv.pair, self._config[CONF_TV_HOST])
            except tv.FrameError as exc:
                _LOGGER.warning("Pairing with the TV failed: %s", exc)
                errors["base"] = "pairing_failed"
            else:
                return self.async_create_entry(title="Frame Energy Art", data={**self._config, CONF_TV_TOKEN: token})
        return self.async_show_form(step_id="pair", data_schema=vol.Schema({}), errors=errors,
                                    description_placeholders={"host": self._config[CONF_TV_HOST]})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return FrameEnergyOptionsFlow()


class FrameEnergyOptionsFlow(config_entries.OptionsFlow):
    """Change sensors, paths or the TV without deleting the integration.

    Home Assistant provides ``self.config_entry``; it must not be assigned here.
    """

    def __init__(self):
        self._options = {}

    async def async_step_init(self, user_input=None):
        current = {**self.config_entry.data, **self.config_entry.options}
        errors = {}
        if user_input is not None:
            options = {**_with_optional(user_input), CONF_TV_HOST: user_input.get(CONF_TV_HOST, "").strip()}
            errors = await _validate(self.hass, options)
            if not options[CONF_TV_HOST]:
                errors[CONF_TV_HOST] = "missing_host"
            if not errors:
                self._options = options
                if options[CONF_TV_HOST] and options[CONF_TV_HOST] != current.get(CONF_TV_HOST):
                    return await self.async_step_pair()
                options[CONF_TV_TOKEN] = current.get(CONF_TV_TOKEN)
                return self.async_create_entry(title="", data=options)
        return self.async_show_form(step_id="init", data_schema=_schema(_with_optional(user_input) if user_input else current), errors=errors)

    async def async_step_pair(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                token = await self.hass.async_add_executor_job(tv.pair, self._options[CONF_TV_HOST])
            except tv.FrameError as exc:
                _LOGGER.warning("Pairing with the TV failed: %s", exc)
                errors["base"] = "pairing_failed"
            else:
                return self.async_create_entry(title="", data={**self._options, CONF_TV_TOKEN: token})
        return self.async_show_form(step_id="pair", data_schema=vol.Schema({}), errors=errors,
                                    description_placeholders={"host": self._options[CONF_TV_HOST]})
