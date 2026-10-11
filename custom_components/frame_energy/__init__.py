"""Generate live art locally and show it on Samsung The Frame.

Upload path:
- built-in uploader when a TV is paired in this integration's options;
- otherwise the separate ``samsung_frame.update`` service (legacy setup).
"""
import asyncio
import logging
from pathlib import Path

import voluptuous as vol
from homeassistant.core import ServiceCall
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import tv
from .const import CONF_TV_HOST, CONF_TV_TOKEN, DOMAIN, ENTITY_DEFAULTS, STORAGE_VERSION
from .render import LABEL_DEFAULTS, render

_LOGGER = logging.getLogger(__name__)


def merged_config(entry):
    return {**entry.data, **entry.options}


async def async_setup_entry(hass, entry):
    store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.uploads")
    saved = await store.async_load() or {}
    paired = merged_config(entry).get(CONF_TV_TOKEN)
    token = saved.get("token") if saved.get("paired_token") == paired else paired
    runtime = {
        "token": token,
        "lock": asyncio.Lock(),
        "last_generated": None,
        "last_upload_attempt": None,
        "last_upload_confirmed": None,
        "content_id": None,
        "uploader": None,
        "error": None,
        "uploaded_ids": list(saved.get("ids", [])),
        "store": store,
    }
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    entry.async_on_unload(entry.add_update_listener(_reload_on_options))
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    async def handle_render(call: ServiceCall):
        async with runtime["lock"]:
            config = merged_config(entry)
            now = dt_util.now()
            snapshot = {}
            for key in ENTITY_DEFAULTS:
                state = hass.states.get(config.get(key, ""))
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
                labels = {key: config.get(key) for key in LABEL_DEFAULTS}
                await hass.async_add_executor_job(render, config["background_path"], config["output_path"], snapshot, forecast, now, labels)
                runtime["last_generated"] = dt_util.utcnow()
                runtime["error"] = None
                async_dispatcher_send(hass, f"{DOMAIN}_updated")
                runtime["last_upload_attempt"] = dt_util.utcnow().isoformat()
                if config.get(CONF_TV_HOST):
                    await _upload_builtin(hass, runtime, config)
                else:
                    await _upload_legacy(hass, runtime, config)
            except Exception as exc:
                runtime["error"] = str(exc)
                _LOGGER.exception("Frame Energy rendering/upload failed")
                raise
            finally:
                async_dispatcher_send(hass, f"{DOMAIN}_updated")

    hass.services.async_register(DOMAIN, "render", handle_render, schema=vol.Schema({}))
    return True


async def _upload_builtin(hass, runtime, config):
    """Upload with confirmation, show it, then delete this project's older images."""
    runtime["uploader"] = "built-in"
    jpeg = await hass.async_add_executor_job(Path(config["output_path"]).read_bytes)
    result = await hass.async_add_executor_job(
        tv.publish, config[CONF_TV_HOST], runtime["token"], jpeg, list(runtime["uploaded_ids"]))
    runtime["content_id"] = result["content_id"]
    runtime["last_upload_confirmed"] = dt_util.utcnow().isoformat()
    # Cap the retry list so an unconfirmed delete on some firmware cannot grow it forever.
    runtime["uploaded_ids"] = [result["content_id"], *result["pending"][:20]]
    if result["token"]:
        runtime["token"] = result["token"]
    await _save(runtime, config)
    if result["delete_error"]:
        _LOGGER.warning("Old artwork kept for retry %s: %s", result["pending"], result["delete_error"])


async def _save(runtime, config):
    # The token is stored next to the token it came from: after a new pairing
    # in the options, the freshly paired token wins over an older stored one.
    await runtime["store"].async_save({
        "ids": runtime["uploaded_ids"],
        "token": runtime["token"],
        "paired_token": config.get(CONF_TV_TOKEN),
    })


async def _upload_legacy(hass, runtime, config):
    """Hand the file to the separate Samsung Frame Art integration (no confirmation)."""
    runtime["uploader"] = "samsung_frame"
    if not hass.services.has_service("samsung_frame", "update"):
        raise RuntimeError("No TV paired here and the samsung_frame.update service is unavailable")
    await hass.services.async_call("samsung_frame", "update", {"image_path": config["output_path"]}, blocking=True)


async def _reload_on_options(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, ["sensor"]):
        hass.services.async_remove(DOMAIN, "render")
        hass.data[DOMAIN].pop(entry.entry_id, None)
        return True
    return False


async def async_remove_entry(hass, entry):
    """Forget stored upload IDs and token when the integration is deleted."""
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.uploads").async_remove()
