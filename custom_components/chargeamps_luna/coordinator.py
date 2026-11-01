"""Polling and actions for Charge Amps Luna."""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AuthenticationError, ChargeAmpsClient, ChargeAmpsError, Charger
from .const import CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL, DOMAIN

LOGGER = logging.getLogger(__name__)
type ChargeAmpsConfigEntry = ConfigEntry[ChargeAmpsCoordinator]


class ChargeAmpsCoordinator(DataUpdateCoordinator[dict[str, Charger]]):
    """One poll for all devices on an account."""

    def __init__(self, hass: HomeAssistant, entry: ChargeAmpsConfigEntry, client: ChargeAmpsClient):
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                minutes=entry.data.get(CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL)
            ),
            always_update=False,
            request_refresh_debouncer=Debouncer(hass, LOGGER, cooldown=0, immediate=True),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Charger]:
        try:
            return await self.client.async_get_chargers()
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ChargeAmpsError as err:
            raise UpdateFailed(str(err)) from err

    async def async_refresh_status(self) -> None:
        """Refresh now and expose failures to the action caller."""
        await self.async_request_refresh()
        if not self.last_update_success:
            raise HomeAssistantError("Could not refresh Charge Amps charger status.")

    async def async_set_mode(self, charger_id: str, connector_id: int, mode: str) -> None:
        try:
            data = await self.client.async_set_mode(charger_id, connector_id, mode)
        except AuthenticationError as err:
            self.async_set_update_error(ConfigEntryAuthFailed(str(err)))
            if self.config_entry:
                self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(str(err)) from err
        except ChargeAmpsError as err:
            # A failed write may have reached the cloud; request its current state.
            await self.async_request_refresh()
            raise HomeAssistantError(str(err)) from err
        self.async_set_updated_data(data)
