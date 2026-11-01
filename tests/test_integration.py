"""Exercise actual Home Assistant entities, actions, polling, and lifecycle."""

from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.chargeamps_luna.api import AuthenticationError, CannotConnect, parse_chargers
from custom_components.chargeamps_luna.config_flow import account_id
from custom_components.chargeamps_luna.const import DOMAIN

CLIENT = "custom_components.chargeamps_luna.api.ChargeAmpsClient"


@pytest.fixture
async def loaded(hass, config_data, raw_chargers):
    entry = MockConfigEntry(domain=DOMAIN, data=config_data, unique_id=account_id(config_data))
    entry.add_to_hass(hass)
    with patch(CLIENT + ".async_get_chargers", return_value=parse_chargers(raw_chargers)) as read:
        with patch(CLIENT + ".async_set_mode") as write:
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
            yield entry, read, write


async def test_entities(hass, loaded):
    entry, read, _ = loaded
    assert entry.state is ConfigEntryState.LOADED
    assert read.await_count == 1
    assert hass.states.get("sensor.luna_status").state == "Online"
    assert hass.states.get("sensor.luna_connector_status").state == "Available"
    assert hass.states.get("binary_sensor.luna_charging").state == "off"
    select = hass.states.get("select.luna_charging_mode")
    assert select.state == "Always on"
    assert select.attributes["options"] == ["Off", "Schedule", "Always on"]
    assert hass.states.get("button.luna_refresh_status") is not None


async def test_manual_refresh_button_and_action(hass, loaded):
    _, read, _ = loaded
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.luna_refresh_status"}, blocking=True
    )
    assert read.await_count == 2
    await hass.services.async_call(DOMAIN, "refresh", {}, blocking=True)
    assert read.await_count == 3


async def test_mode_selector(hass, loaded, raw_chargers):
    _, _, write = loaded
    raw_chargers[0]["connectors"][0]["mode"] = "Schedule"
    write.return_value = parse_chargers(raw_chargers)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.luna_charging_mode", "option": "Schedule"},
        blocking=True,
    )
    write.assert_awaited_once_with("test-luna", 1, "Schedule")
    assert hass.states.get("select.luna_charging_mode").state == "Schedule"


async def test_default_polling_interval(hass, freezer, loaded):
    entry, read, _ = loaded
    assert entry.runtime_data.update_interval == timedelta(minutes=15)
    freezer.tick(timedelta(minutes=14))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert read.await_count == 1
    freezer.tick(timedelta(minutes=2))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert read.await_count == 2


async def test_refresh_failure_marks_unavailable_but_button_recovers(hass, loaded):
    _, read, _ = loaded
    read.side_effect = CannotConnect("Temporary connection failure")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(DOMAIN, "refresh", {}, blocking=True)
    assert hass.states.get("sensor.luna_status").state == "unavailable"
    assert hass.states.get("button.luna_refresh_status").state != "unavailable"
    read.side_effect = None
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.luna_refresh_status"}, blocking=True
    )
    assert hass.states.get("sensor.luna_status").state == "Online"


async def test_new_and_removed_chargers(hass, loaded, raw_chargers):
    entry, _, _ = loaded
    additional = deepcopy(raw_chargers[0])
    additional.update(id="second-luna", name="Garage")
    entry.runtime_data.async_set_updated_data(parse_chargers(raw_chargers + [additional]))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.garage_status").state == "Online"
    entry.runtime_data.async_set_updated_data({})
    assert hass.states.get("sensor.luna_status").state == "unavailable"
    assert hass.states.get("select.luna_charging_mode").state == "unavailable"


async def test_unload_stops_entities_and_polling(hass, loaded, freezer):
    entry, read, _ = loaded
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert hass.states.get("sensor.luna_status").state == "unavailable"
    freezer.tick(timedelta(hours=1))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert read.await_count == 1


async def test_bad_credentials_start_reauth(hass, config_data):
    entry = MockConfigEntry(domain=DOMAIN, data=config_data, unique_id=account_id(config_data))
    entry.add_to_hass(hass)
    with patch(CLIENT + ".async_get_chargers", side_effect=AuthenticationError("Rejected")):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(flow["context"]["source"] == "reauth" for flow in flows)
