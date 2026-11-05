"""Protocol tests for login, refresh, and CSRF-protected mode changes."""

import json
import re
from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, datetime
from types import SimpleNamespace

import aioresponses.core as response_core
import pytest
from aiohttp import ClientResponse, ClientSession
from aioresponses import aioresponses

from custom_components.chargeamps_luna.api import (
    AuthenticationError,
    ChargeAmpsClient,
    ModeError,
    normalize_url,
    parse_chargers,
    parse_lifetime_energy,
)

API = "https://my.charge.space/userapp/api"
OWNED = API + "/users/chargepoints/owned?expand=ocppConfig,topChargingLimitation"
ENERGY = re.compile(re.escape(API + "/chargepoints/test-luna/consumption-data?") + ".*")
LOGIN = {}
METER = {
    "series": [
        {
            "connectorId": 1,
            "data": [
                {
                    "bucketStartUtc": "2026-11-05T20:05:00Z",
                    "lastObservedAtUtc": "2026-11-05T20:09:45Z",
                    "lifetimeEnergyWh": 6169410,
                }
            ],
        }
    ]
}


@pytest.fixture(autouse=True)
def current_aiohttp_response(monkeypatch):
    """aioresponses 0.7.9 predates aiohttp 3.14's stream_writer argument."""

    class TestResponse(ClientResponse):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("stream_writer", SimpleNamespace(output_size=0))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(response_core, "ClientResponse", TestResponse)


@pytest.mark.parametrize(
    "value",
    [
        "my.charge.space",
        "https://MY.charge.space/",
        "https://my.charge.space/userapp/",
        "https://my.charge.space:443",
    ],
)
def test_url_normalization(value):
    assert normalize_url(value) == "https://my.charge.space"


@pytest.mark.parametrize(
    "value",
    [
        "http://my.charge.space",
        "https://user:pass@my.charge.space",
        "https://my.charge.space?secret=1",
        "https://my.charge.space/other",
        "https://bad host",
    ],
)
def test_invalid_urls(value):
    with pytest.raises(ValueError):
        normalize_url(value)


def test_models_exclude_secrets(raw_chargers):
    result = parse_chargers(raw_chargers)
    serialized = json.dumps(asdict(result["test-luna"]))
    assert all(
        secret not in serialized for secret in ("PRIVATE_WIFI", "PRIVATE_EMAIL", "PRIVATE_TAG")
    )


async def test_poll_reuses_session_and_renews_on_401(raw_chargers):
    with aioresponses() as responses:
        responses.post(API + "/auth/login", payload={**LOGIN, "token": "PRIVATE_TOKEN"})
        responses.get(OWNED, payload=raw_chargers)
        responses.get(ENERGY, payload=METER, repeat=True)
        responses.get(OWNED, status=401)
        responses.post(API + "/auth/login", payload=LOGIN)
        responses.get(OWNED, payload=raw_chargers)
        async with ClientSession() as session:
            client = ChargeAmpsClient(session, "my.charge.space", "user", "secret")
            first = await client.async_get_chargers()
            assert first == await client.async_get_chargers()
            assert first["test-luna"].connectors[0].total_energy_kwh == 6169.41
            assert first["test-luna"].connectors[0].session_energy_kwh == 3.945984
        assert (
            sum(len(calls) for (method, _), calls in responses.requests.items() if method == "POST")
            == 2
        )
        assert (
            sum(
                len(calls)
                for (_, url), calls in responses.requests.items()
                if "/consumption-data?" in str(url)
            )
            == 2
        )


async def test_login_error_does_not_include_response_or_password():
    with aioresponses() as responses:
        responses.post(API + "/auth/login", status=401, payload={"echo": "PRIVATE_PASSWORD"})
        async with ClientSession() as session:
            client = ChargeAmpsClient(session, "my.charge.space", "user", "PRIVATE_PASSWORD")
            with pytest.raises(AuthenticationError) as error:
                await client.async_get_chargers()
            assert "PRIVATE_PASSWORD" not in str(error.value)


async def test_login_drops_empty_scoped_access_deletion_cookies(raw_chargers):
    """Empty cookies returned by login must not turn a normal session into scoped access."""
    from aioresponses import CallbackResult

    with aioresponses() as responses:
        async with ClientSession() as session:

            def login(url, **kwargs):
                session.cookie_jar.update_cookies(
                    {
                        "ca_session": "test-session",
                        "ca_scoped_access": "",
                        "ca_ent_context": "",
                        "ca_csrf": "",
                    }
                )
                return CallbackResult(payload=LOGIN)

            responses.post(API + "/auth/login", callback=login)
            responses.get(OWNED, payload=raw_chargers)
            responses.get(ENERGY, payload=METER)
            await ChargeAmpsClient(
                session, "my.charge.space", "user", "secret"
            ).async_get_chargers()
            assert [cookie.key for cookie in session.cookie_jar] == ["ca_session"]


@pytest.mark.parametrize(
    "mode,previous,portal_mode",
    [("Off", "On", "Off"), ("Schedule", "On", "Schedule"), ("Always on", "Off", "On")],
)
async def test_mode_change_preserves_configuration_and_verifies(
    raw_chargers, mode, previous, portal_mode
):
    raw_chargers[0]["connectors"][0]["mode"] = previous
    before = deepcopy(raw_chargers)
    expected = deepcopy(raw_chargers[0])
    expected["connectors"][0]["mode"] = portal_mode
    with aioresponses() as responses:
        responses.post(API + "/auth/login", payload=LOGIN)
        responses.get(OWNED, payload=raw_chargers)
        if mode == "Schedule":
            responses.get(
                API + "/smartChargingSchedules/chargepoint/test-luna", payload=[{"connectorId": 1}]
            )
        responses.get(API + "/csrf/handshake", payload={}, headers={"X-CSRF-TOKEN": "csrf-token"})

        def check_write(url, **kwargs):
            assert kwargs["json"] == expected
            assert kwargs["headers"]["X-CSRF-TOKEN"] == "csrf-token"
            from aioresponses import CallbackResult

            return CallbackResult(status=204)

        responses.put(API + "/chargepoints", callback=check_write)
        responses.get(OWNED, payload=[expected])
        responses.get(ENERGY, payload=METER)
        async with ClientSession() as session:
            result = await ChargeAmpsClient(
                session, "my.charge.space", "user", "secret"
            ).async_set_mode("test-luna", 1, mode)
        assert result["test-luna"].connectors[0].mode == mode
        assert result["test-luna"].connectors[0].total_energy_kwh == 6169.41
        assert raw_chargers == before


async def test_no_schedule_never_writes(raw_chargers):
    with aioresponses() as responses:
        responses.post(API + "/auth/login", payload=LOGIN)
        responses.get(OWNED, payload=raw_chargers)
        responses.get(API + "/smartChargingSchedules/chargepoint/test-luna", payload=[])
        async with ClientSession() as session:
            with pytest.raises(ModeError, match="Create a schedule"):
                await ChargeAmpsClient(session, "my.charge.space", "user", "secret").async_set_mode(
                    "test-luna", 1, "Schedule"
                )
        assert not any(method == "PUT" for method, _ in responses.requests)


async def test_csrf_rejected_once_then_refreshed(raw_chargers):
    after = deepcopy(raw_chargers)
    after[0]["connectors"][0]["mode"] = "Off"
    with aioresponses() as responses:
        responses.post(API + "/auth/login", payload=LOGIN)
        responses.get(OWNED, payload=raw_chargers)
        responses.get(API + "/csrf/handshake", payload={}, headers={"X-CSRF-TOKEN": "old"})
        responses.put(API + "/chargepoints", status=403)
        responses.get(API + "/csrf/handshake", payload={}, headers={"X-CSRF-TOKEN": "new"})
        responses.put(API + "/chargepoints", status=204)
        responses.get(OWNED, payload=after)
        responses.get(ENERGY, payload=METER)
        async with ClientSession() as session:
            await ChargeAmpsClient(session, "my.charge.space", "user", "secret").async_set_mode(
                "test-luna", 1, "Off"
            )
        writes = [
            call
            for (method, _), calls in responses.requests.items()
            if method == "PUT"
            for call in calls
        ]
        assert [call.kwargs["headers"]["X-CSRF-TOKEN"] for call in writes] == ["old", "new"]


async def test_timeout_does_not_repeat_write(raw_chargers):
    with aioresponses() as responses:
        responses.post(API + "/auth/login", payload=LOGIN)
        responses.get(OWNED, payload=raw_chargers)
        responses.get(API + "/csrf/handshake", payload={}, headers={"X-CSRF-TOKEN": "token"})
        responses.put(API + "/chargepoints", exception=TimeoutError())
        async with ClientSession() as session:
            with pytest.raises(ModeError, match="outcome is unknown"):
                await ChargeAmpsClient(session, "my.charge.space", "user", "secret").async_set_mode(
                    "test-luna", 1, "Off"
                )
        assert (
            sum(len(calls) for (method, _), calls in responses.requests.items() if method == "PUT")
            == 1
        )


def test_energy_units_latest_sample_and_invalid_values(raw_chargers):
    assert parse_chargers(raw_chargers)["test-luna"].connectors[0].session_energy_kwh == 3.945984
    del raw_chargers[0]["connectors"][0]["totalConsumptionKwh"]
    assert parse_chargers(raw_chargers)["test-luna"].connectors[0].session_energy_kwh == 3.945984
    data = deepcopy(METER)
    rows = data["series"][0]["data"]
    rows.append({"bucketStartUtc": "2026-11-05T19:00:00Z", "lifetimeEnergyWh": 9000000})
    for invalid in [None, True, -1, "123", float("nan"), float("inf")]:
        rows.append({"bucketStartUtc": "2026-11-06T00:00:00Z", "lifetimeEnergyWh": invalid})
    assert parse_lifetime_energy(data) == {
        1: (6169.41, datetime(2026, 11, 5, 20, 9, 45, tzinfo=UTC))
    }


async def test_energy_failure_and_empty_idle_window_never_report_zero(raw_chargers):
    with aioresponses() as responses:
        responses.post(API + "/auth/login", payload={})
        responses.get(OWNED, payload=raw_chargers, repeat=True)
        responses.get(ENERGY, payload=METER)
        responses.get(ENERGY, status=503, payload={"error": "PRIVATE_RESPONSE"})
        responses.get(ENERGY, payload={"series": [{"connectorId": 1, "data": []}]})
        older = deepcopy(METER)
        older["series"][0]["data"][0].update(
            lastObservedAtUtc="2026-11-05T20:00:00Z", lifetimeEnergyWh=6168000
        )
        responses.get(ENERGY, payload=older)
        async with ClientSession() as session:
            client = ChargeAmpsClient(session, "my.charge.space", "user", "secret")
            assert (await client.async_get_chargers())["test-luna"].connectors[
                0
            ].total_energy_kwh == 6169.41
            failed = (await client.async_get_chargers())["test-luna"]
            assert failed.status == "Online"
            assert failed.connectors[0].total_energy_kwh is None
            assert client.energy_error and "PRIVATE_RESPONSE" not in client.energy_error
            for _ in range(2):
                recovered = (await client.async_get_chargers())["test-luna"].connectors[0]
                assert recovered.total_energy_kwh == 6169.41
                assert recovered.energy_sampled_at == "2026-11-05T20:09:45+00:00"
                assert client.energy_error is None


async def test_idle_startup_fallback_keeps_connectors_separate_and_accepts_zero(raw_chargers):
    raw_chargers[0]["connectors"].append({"connectorId": 2})
    daily = {
        "series": [
            {
                "connectorId": 1,
                "data": [{"bucketStartUtc": "2026-10-01T00:00:00Z", "lifetimeEnergyWh": 1234567}],
            },
            {
                "connectorId": 2,
                "data": [{"bucketStartUtc": "2026-10-01T00:00:00Z", "lifetimeEnergyWh": 0}],
            },
        ]
    }
    with aioresponses() as responses:
        responses.post(API + "/auth/login", payload={})
        responses.get(OWNED, payload=raw_chargers, repeat=True)
        responses.get(ENERGY, payload={"series": []})
        responses.get(ENERGY, payload={"series": []})
        responses.get(ENERGY, payload=daily)
        responses.get(ENERGY, payload={"series": []})
        async with ClientSession() as session:
            client = ChargeAmpsClient(session, "my.charge.space", "user", "secret")
            for _ in range(2):
                connectors = (await client.async_get_chargers())["test-luna"].connectors
                assert [c.total_energy_kwh for c in connectors] == [1234.567, 0]
        # Three startup requests, then just one short-window request while idle.
        calls = [
            call
            for (method, url), group in responses.requests.items()
            if "/consumption-data?" in str(url)
            for call in group
        ]
        assert len(calls) == 4
        assert sum("resolution=1d" in str(url) for method, url in responses.requests) == 1
