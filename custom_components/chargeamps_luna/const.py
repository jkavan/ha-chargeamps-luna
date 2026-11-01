"""Constants for Charge Amps Luna."""

DOMAIN = "chargeamps_luna"
DEFAULT_URL = "https://my.charge.space"
CONF_REFRESH_INTERVAL = "refresh_interval"
DEFAULT_REFRESH_INTERVAL = 15  # Minutes.
MODE_TO_PORTAL = {"Off": "Off", "Schedule": "Schedule", "Always on": "On"}
PORTAL_TO_MODE = {value: key for key, value in MODE_TO_PORTAL.items()}
