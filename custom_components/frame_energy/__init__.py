"""Generate live art locally and show it on Samsung The Frame."""
import asyncio
import functools
import logging
from pathlib import Path

import voluptuous as vol
from homeassistant.core import ServiceCall, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import schedule, tv
from .const import (CONF_SHOW_UPDATE_TIME, CONF_TV_HOST, CONF_TV_TOKEN, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL,
                    DOMAIN, ENTITY_DEFAULTS, SCHEDULE_SECOND, STARTUP_DELAY, STORAGE_VERSION)
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
        "error": None,
        "uploaded_ids": list(saved.get("ids", [])),
        "late_ids": [],  # IDs the TV confirmed to an upload that never finished
        "store": store,
    }
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    entry.async_on_unload(entry.add_update_listener(_reload_on_options))
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    async def handle_render(call: ServiceCall):
        await _render_and_upload()

    async def _render_and_upload():
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
                cars = [key for key in ("tesla", "hyundai") if config.get(key)]  # empty field = no such car
                await hass.async_add_executor_job(render, config.get("background_path"), config["output_path"], snapshot, forecast,
                                                  now, labels, cars, bool(config.get(CONF_SHOW_UPDATE_TIME)))
                runtime["last_generated"] = dt_util.utcnow()
                runtime["error"] = None
                async_dispatcher_send(hass, f"{DOMAIN}_updated")
                runtime["last_upload_attempt"] = dt_util.utcnow().isoformat()
                await _upload(hass, runtime, config)
            except Exception as exc:
                runtime["error"] = str(exc)
                _LOGGER.exception("Frame Energy rendering/upload failed")
                raise
            finally:
                async_dispatcher_send(hass, f"{DOMAIN}_updated")

    hass.services.async_register(DOMAIN, "render", handle_render, schema=vol.Schema({}))

    minutes = schedule.interval_minutes(merged_config(entry).get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
    if minutes:
        async def scheduled_update(_now=None):
            if schedule.should_skip(runtime["lock"].locked(), runtime["last_generated"], dt_util.utcnow(), minutes):
                _LOGGER.debug("Scheduled update skipped: a picture was just made or an update is running")
                return
            try:
                await _render_and_upload()
            except Exception:  # already logged and shown on the status sensor
                pass

        @callback
        def start_update(now=None):
            entry.async_create_background_task(hass, scheduled_update(now), f"{DOMAIN} scheduled update")

        entry.async_on_unload(async_track_time_change(
            hass, start_update, minute=schedule.schedule_minutes(minutes), second=SCHEDULE_SECOND))
        entry.async_on_unload(async_call_later(hass, STARTUP_DELAY, start_update))
    return True


async def _upload(hass, runtime, config):
    """Upload with confirmation, show it, then delete this project's older images."""
    if not config.get(CONF_TV_HOST):
        raise RuntimeError("No TV paired: open Configure on Frame Energy Art and enter the TV IP address")
    jpeg = await hass.async_add_executor_job(Path(config["output_path"]).read_bytes)
    _merge_late(runtime)
    publish = functools.partial(
        tv.publish, config[CONF_TV_HOST], runtime["token"], jpeg, list(runtime["uploaded_ids"]),
        confirmed=runtime["late_ids"])
    try:
        # tv.publish has its own time limit. This is the second safety net: a
        # stuck update must end with an error, never hold the lock for hours.
        result = await asyncio.wait_for(hass.async_add_executor_job(publish), timeout=tv.TOTAL_TIMEOUT + 30)
    except asyncio.TimeoutError as exc:
        _merge_late(runtime)
        await _save(runtime, config)
        raise RuntimeError("The TV did not finish the upload in time") from exc
    except asyncio.CancelledError:
        _merge_late(runtime)  # for example the automation was restarted
        raise
    runtime["content_id"] = result["content_id"]
    runtime["last_upload_confirmed"] = dt_util.utcnow().isoformat()
    # Never drop an ID: a forgotten ID is a picture left on the TV forever.
    # If deletes keep failing, pending_deletes on the status sensor grows.
    runtime["uploaded_ids"] = [result["content_id"], *result["pending"]]
    if result["token"]:
        runtime["token"] = result["token"]
    await _save(runtime, config)
    runtime["error"] = result["delete_error"]  # the upload worked, but show it on the sensor
    if result["delete_error"]:
        _LOGGER.warning("Old artwork kept for retry %s: %s", result["pending"], result["delete_error"])


def _merge_late(runtime):
    """Move IDs confirmed by a stuck or cancelled upload into the retry list.

    A picture the TV confirmed is on the TV, so its ID must not be forgotten.
    The list may still grow while a stuck thread ends later, so only the part
    already read is removed.
    """
    late = runtime["late_ids"]
    seen = list(late)
    for content_id in seen:
        if content_id not in runtime["uploaded_ids"]:
            runtime["uploaded_ids"].append(content_id)
    del late[:len(seen)]


async def _save(runtime, config):
    # The token is stored next to the token it came from: after a new pairing
    # in the options, the freshly paired token wins over an older stored one.
    await runtime["store"].async_save({
        "ids": runtime["uploaded_ids"],
        "token": runtime["token"],
        "paired_token": config.get(CONF_TV_TOKEN),
    })


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
