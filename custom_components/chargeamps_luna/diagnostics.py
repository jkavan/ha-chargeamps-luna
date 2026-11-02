"""Download diagnostic state without credentials or charger identities."""

from dataclasses import asdict
from typing import Any

from homeassistant.core import HomeAssistant

from .const import CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL
from .coordinator import ChargeAmpsConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ChargeAmpsConfigEntry
) -> dict[str, Any]:
    """Use the sanitized cached models; downloading never triggers a poll."""
    coordinator = entry.runtime_data
    chargers = []
    for charger in coordinator.data.values():
        data = asdict(charger)
        del data["id"]
        del data["name"]
        chargers.append(data)
    refreshed = coordinator.last_update_success_time
    return {
        "refresh_interval_minutes": entry.data.get(CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL),
        "portal_connected": coordinator.last_update_success,
        "last_successful_refresh": refreshed.isoformat() if refreshed else None,
        "last_refresh_error": coordinator.refresh_error,
        "chargers": chargers,
    }
