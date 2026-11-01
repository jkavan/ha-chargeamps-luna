"""Setup, reconfiguration, and reauthentication flows."""

from hashlib import sha256
from typing import Any

import probatio as vol
from aiohttp import CookieJar
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import AuthenticationError, CannotConnect, ChargeAmpsClient, normalize_url
from .const import CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL, DEFAULT_URL, DOMAIN


def account_id(data: dict) -> str:
    """Stable identifier without putting the login name in entity IDs."""
    return sha256(f"{data[CONF_URL]}\0{data[CONF_USERNAME].casefold()}".encode()).hexdigest()


async def async_validate_input(hass, data: dict) -> bool:
    """Validate credentials and charger access without persisting a session."""
    session = async_create_clientsession(hass, auto_cleanup=False, cookie_jar=CookieJar())
    try:
        client = ChargeAmpsClient(session, data[CONF_URL], data[CONF_USERNAME], data[CONF_PASSWORD])
        return bool(await client.async_get_chargers())
    finally:
        # Home Assistant owns the shared connector; detach this temporary session.
        session.detach()


class ChargeAmpsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure a portal account and refresh interval in minutes."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._async_form("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_form("reconfigure", user_input, self._get_reconfigure_entry())

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_form("reauth_confirm", user_input, self._get_reauth_entry())

    async def _async_form(
        self, step: str, user_input: dict[str, Any] | None, entry: ConfigEntry | None = None
    ) -> ConfigFlowResult:
        errors = {}
        defaults = (
            dict(entry.data)
            if entry
            else {
                CONF_URL: DEFAULT_URL,
                CONF_REFRESH_INTERVAL: DEFAULT_REFRESH_INTERVAL,
            }
        )
        if user_input is not None:
            data = {**defaults, **user_input}
            data[CONF_USERNAME] = data[CONF_USERNAME].strip()
            if entry and not data.get(CONF_PASSWORD):
                data[CONF_PASSWORD] = entry.data[CONF_PASSWORD]
            try:
                data[CONF_URL] = normalize_url(data[CONF_URL])
            except ValueError:
                errors[CONF_URL] = "invalid_url"
            else:
                try:
                    has_chargers = await async_validate_input(self.hass, data)
                except AuthenticationError:
                    errors["base"] = "invalid_auth"
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                else:
                    if not has_chargers:
                        errors["base"] = "no_chargers"
                    else:
                        unique_id = account_id(data)
                        await self.async_set_unique_id(unique_id)
                        if entry:
                            if any(
                                other.entry_id != entry.entry_id and other.unique_id == unique_id
                                for other in self._async_current_entries()
                            ):
                                return self.async_abort(reason="already_configured")
                            return self.async_update_reload_and_abort(
                                entry,
                                data=data,
                                unique_id=unique_id,
                                title=f"Charge Amps ({data[CONF_USERNAME]})",
                            )
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(
                            title=f"Charge Amps ({data[CONF_USERNAME]})", data=data
                        )
            defaults.update(user_input)
        fields = {
            vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): TextSelector(),
            (vol.Optional(CONF_PASSWORD) if entry else vol.Required(CONF_PASSWORD)): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_URL, default=defaults.get(CONF_URL, DEFAULT_URL)): TextSelector(),
            vol.Required(
                CONF_REFRESH_INTERVAL,
                default=defaults.get(CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
        }
        return self.async_show_form(step_id=step, data_schema=vol.Schema(fields), errors=errors)
