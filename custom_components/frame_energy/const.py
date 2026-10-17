DOMAIN = "frame_energy"
CONF_TV_HOST = "tv_host"
CONF_TV_TOKEN = "tv_token"
STORAGE_VERSION = 1

PATH_DEFAULTS = {
    "background_path": "",  # empty = the painting built into the integration
    "output_path": "/media/frame/frame_energy_live.jpg",
}
ENTITY_DEFAULTS = {
    "solar": "sensor.solar_power",
    "home": "sensor.home_power",
    "battery": "sensor.home_battery_percentage",
    "battery_charge": "sensor.battery_charging_power",
    "battery_discharge": "sensor.battery_discharging_power",
    "tesla": "sensor.tesla_battery_level",
    "tesla_power": "sensor.tesla_charging_power",
    "hyundai": "sensor.hyundai_battery_level",
    "hyundai_power": "sensor.hyundai_charging_power",
    "weather": "weather.home",
}
DEFAULTS = {**PATH_DEFAULTS, **ENTITY_DEFAULTS}
# Car sensors may be left empty: an empty first/second car is not drawn.
CAR_KEYS = ("tesla", "tesla_power", "hyundai", "hyundai_power")
# Fields that may be cleared in the setup form.
OPTIONAL_KEYS = ("background_path", *CAR_KEYS)
CONF_SHOW_UPDATE_TIME = "show_update_time"
# How often the integration updates the picture by itself.
# "manual" = only when frame_energy.render is called (for example by your own automation).
CONF_UPDATE_INTERVAL = "update_interval"
UPDATE_INTERVALS = ("5", "10", "15", "30", "60", "manual")
DEFAULT_UPDATE_INTERVAL = "15"
STARTUP_DELAY = 60  # seconds after start, so the sensors have their values first
SCHEDULE_SECOND = 30  # run at hh:mm:30, a little after an automation that runs at hh:mm:00
