from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([FrameEnergyStatus(hass.data[DOMAIN][entry.entry_id])])

class FrameEnergyStatus(SensorEntity):
    _attr_name = "Frame Energy Last Generated"
    _attr_unique_id = "frame_energy_last_generated"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(self, runtime):
        self.runtime = runtime

    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(self.hass, f"{DOMAIN}_updated", self.async_write_ha_state))

    @property
    def native_value(self):
        return self.runtime["last_generated"]

    @property
    def extra_state_attributes(self):
        r = self.runtime
        return {
            "uploader": r["uploader"],
            "last_upload_attempt": r["last_upload_attempt"],
            # Only the built-in uploader can confirm that the TV accepted the image.
            "last_upload_confirmed": r["last_upload_confirmed"],
            "content_id": r["content_id"],
            "pending_deletes": max(len(r["uploaded_ids"]) - 1, 0),
            "error": r["error"],
        }
