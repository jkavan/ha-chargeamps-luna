"""Charge Amps Luna custom integration."""

import asyncio

import probatio as vol
from aiohttp import CookieJar
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import ChargeAmpsClient
from .const import DOMAIN
from .coordinator import ChargeAmpsConfigEntry, ChargeAmpsCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SELECT, Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the user-triggered refresh action."""

    async def refresh(call: ServiceCall) -> None:
        coordinators = [
            entry.runtime_data
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]
        if not coordinators:
            raise HomeAssistantError("No Charge Amps accounts are loaded.")
        await asyncio.gather(*(coordinator.async_refresh_status() for coordinator in coordinators))

    hass.services.async_register(DOMAIN, "refresh", refresh, schema=vol.Schema({}))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ChargeAmpsConfigEntry) -> bool:
    """Create an isolated session, poll, and load platforms."""
    session = async_create_clientsession(hass, cookie_jar=CookieJar())
    client = ChargeAmpsClient(
        session, entry.data[CONF_URL], entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD]
    )
    coordinator = ChargeAmpsCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ChargeAmpsConfigEntry) -> bool:
    """Unload entities and their session/polling callbacks."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
