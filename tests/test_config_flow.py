"""Exercise setup, error handling, reconfiguration, and reauthentication."""

from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.chargeamps_luna.api import AuthenticationError, CannotConnect
from custom_components.chargeamps_luna.config_flow import account_id
from custom_components.chargeamps_luna.const import DOMAIN

VALIDATE = "custom_components.chargeamps_luna.config_flow.async_validate_input"


async def test_setup_defaults_and_saved_fields(hass, config_data):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    defaults = {
        key.schema: key.default()
        for key in result["data_schema"].schema
        if key.default is not None and key.schema in ("url", "refresh_interval")
    }
    assert defaults == {"url": "https://my.charge.space", "refresh_interval": 15}
    with (
        patch(VALIDATE, return_value=True),
        patch("custom_components.chargeamps_luna.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**config_data, "url": "my.charge.space"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == config_data


@pytest.mark.parametrize(
    "error,expected", [(AuthenticationError(), "invalid_auth"), (CannotConnect(), "cannot_connect")]
)
async def test_setup_errors(hass, config_data, error, expected):
    with patch(VALIDATE, side_effect=error):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}, data=config_data
        )
    assert result["errors"] == {"base": expected}


async def test_invalid_url_and_empty_account(hass, config_data):
    with patch(VALIDATE, return_value=False) as validate:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data={**config_data, "url": "http://my.charge.space"},
        )
        assert result["errors"] == {"url": "invalid_url"}
        validate.assert_not_called()
        result = await hass.config_entries.flow.async_configure(result["flow_id"], config_data)
        assert result["errors"] == {"base": "no_chargers"}


async def test_duplicate_account(hass, config_data):
    entry = MockConfigEntry(domain=DOMAIN, data=config_data, unique_id=account_id(config_data))
    entry.add_to_hass(hass)
    with patch(VALIDATE, return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}, data=config_data
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_all_fields_can_be_reconfigured(hass, config_data):
    entry = MockConfigEntry(domain=DOMAIN, data=config_data, unique_id=account_id(config_data))
    entry.add_to_hass(hass)
    changed = {
        "username": "new@example.test",
        "password": "new-secret",
        "url": "https://portal.example.test",
        "refresh_interval": 5,
    }
    with (
        patch(VALIDATE, return_value=True) as validate,
        patch.object(hass.config_entries, "async_reload", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}, data=changed
        )
        await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == changed
    assert validate.call_args.args[1] == changed


async def test_reconfigure_blank_password_preserves_it(hass, config_data):
    entry = MockConfigEntry(domain=DOMAIN, data=config_data, unique_id=account_id(config_data))
    entry.add_to_hass(hass)
    with (
        patch(VALIDATE, return_value=True),
        patch.object(hass.config_entries, "async_reload", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
            data={**config_data, "password": "", "refresh_interval": 30},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert entry.data["password"] == "test-password"
    assert entry.data["refresh_interval"] == 30


async def test_reauth(hass, config_data):
    entry = MockConfigEntry(domain=DOMAIN, data=config_data, unique_id=account_id(config_data))
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id}, data=config_data
    )
    assert result["step_id"] == "reauth_confirm"
    with (
        patch(VALIDATE, return_value=True),
        patch.object(hass.config_entries, "async_reload", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**config_data, "password": "new-secret"}
        )
        await hass.async_block_till_done()
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "new-secret"
