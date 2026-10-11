"""Generate live art locally; the existing Samsung integration uploads it."""
import asyncio
import logging
import voluptuous as vol
from homeassistant.core import ServiceCall
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util
from .const import DOMAIN
from .render import render

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry):
    runtime = {"lock": asyncio.Lock(), "last_generated": None, "last_upload_attempt": None, "error": None}
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    async def handle_render(call: ServiceCall):
        async with runtime["lock"]:
            config = entry.data
            now = dt_util.now()
            snapshot = {}
            for key, entity_id in config.items():
                if key.endswith("_path"):
                    continue
                state = hass.states.get(entity_id)
                snapshot[key] = None if state is None else {
                    "state": state.state,
                    "attributes": dict(state.attributes),
                    "updated": state.last_updated.isoformat(),
                }
            forecast = []
            try:
                response = await hass.services.async_call("weather", "get_forecasts",
                    {"entity_id": config["weather"], "type": "daily"}, blocking=True, return_response=True)
                forecast = (response or {}).get(config["weather"], {}).get("forecast", [])
            except Exception as exc:
                _LOGGER.warning("Forecast unavailable: %s", exc)
            try:
                await hass.async_add_executor_job(render, config["background_path"], config["output_path"], snapshot, forecast, now)
                runtime["last_generated"] = dt_util.utcnow()
                runtime["error"] = None
                async_dispatcher_send(hass, f"{DOMAIN}_updated")
                # Generation completes before the TV receives the named file.
                # The third-party service logs upload failures without raising;
                # this timestamp deliberately records an ATTEMPT, not delivery.
                if not hass.services.has_service("samsung_frame", "update"):
                    raise RuntimeError("Samsung Frame update service is unavailable")
                runtime["last_upload_attempt"] = dt_util.utcnow().isoformat()
                await hass.services.async_call("samsung_frame", "update",
                    {"image_path": config["output_path"]}, blocking=True)
            except Exception as exc:
                runtime["error"] = str(exc)
                _LOGGER.exception("Frame Energy rendering/upload failed")
                raise
            finally:
                async_dispatcher_send(hass, f"{DOMAIN}_updated")

    hass.services.async_register(DOMAIN, "render", handle_render, schema=vol.Schema({}))
    return True

async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, ["sensor"]):
        hass.services.async_remove(DOMAIN, "render")
        hass.data[DOMAIN].pop(entry.entry_id, None)
        return True
    return False
