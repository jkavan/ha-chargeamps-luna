"""Async client for the Charge Amps website's private HTTPS interface.

Only this module handles raw portal data. Public models intentionally omit
account details, Wi-Fi credentials, cookies, and authentication tokens.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import aiohttp

from .const import MODE_TO_PORTAL, PORTAL_TO_MODE


class ChargeAmpsError(Exception):
    """Base error containing only a safe, user-facing message."""


class AuthenticationError(ChargeAmpsError):
    """Credentials were rejected."""


class CannotConnect(ChargeAmpsError):
    """The portal could not be reached or returned an invalid response."""


class ModeError(ChargeAmpsError):
    """The requested mode could not be applied or confirmed."""


class _HTTPError(ChargeAmpsError):
    def __init__(self, status: int):
        self.status = status
        super().__init__(f"The portal returned HTTP {status}.")


def normalize_url(value: str) -> str:
    """Accept a bare hostname or HTTPS portal origin, never URL credentials."""
    value = value.strip()
    if "://" not in value:
        value = "https://" + value
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        raise ValueError("Enter a valid HTTPS portal URL.") from None
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or parts.path.rstrip("/") not in ("", "/userapp")
        or any(character.isspace() for character in parts.netloc)
    ):
        raise ValueError("Enter the HTTPS portal origin, such as https://my.charge.space.")
    host = parts.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    if port and port != 443:
        host += f":{port}"
    return urlunsplit(("https", host, "", "", ""))


@dataclass(frozen=True)
class Connector:
    """Safe connector state."""

    id: int
    status: str | None
    mode: str | None
    is_charging: bool | None
    error_code: str | None


@dataclass(frozen=True)
class Charger:
    """Safe charger state."""

    id: str
    name: str
    model: str
    firmware: str | None
    status: str | None
    read_only: bool
    externally_managed: bool
    connectors: tuple[Connector, ...]


def parse_chargers(data: Any) -> dict[str, Charger]:
    """Validate a portal response and discard all non-status fields."""
    if not isinstance(data, list):
        raise CannotConnect("The portal returned an unexpected charger response.")
    result = {}
    for raw in data:
        if (
            not isinstance(raw, dict)
            or not isinstance(raw.get("id"), str)
            or not raw["id"]
            or not isinstance(raw.get("connectors"), list)
            or "chargePointStatus" not in raw
        ):
            raise CannotConnect("The portal's charger response format has changed.")
        connectors = []
        seen = set()
        for connector in raw["connectors"]:
            if (
                not isinstance(connector, dict)
                or type(connector.get("connectorId")) is not int
                or connector["connectorId"] in seen
            ):
                raise CannotConnect("The portal returned an invalid connector response.")
            seen.add(connector["connectorId"])
            connectors.append(
                Connector(
                    id=connector["connectorId"],
                    status=connector.get("ocppStatus") or connector.get("evConnectorState"),
                    mode=PORTAL_TO_MODE.get(connector.get("mode")),
                    is_charging=connector.get("isCharging")
                    if isinstance(connector.get("isCharging"), bool)
                    else None,
                    error_code=connector.get("errorCode"),
                )
            )
        if raw["id"] in result:
            raise CannotConnect("The portal returned duplicate charger identifiers.")
        result[raw["id"]] = Charger(
            id=raw["id"],
            name=raw.get("name") or raw["id"],
            model=raw.get("productName") or "Luna",
            firmware=raw.get("installedFirmwareVersion"),
            status=raw.get("chargePointStatus"),
            read_only=bool(raw.get("ownerReadOnly")),
            externally_managed=bool(raw.get("ocppEnabled")),
            connectors=tuple(connectors),
        )
    return result


class ChargeAmpsClient:
    """Account-isolated cookie session; serialize polls and mode updates."""

    def __init__(self, session: aiohttp.ClientSession, url: str, username: str, password: str):
        self.session = session
        self.url = normalize_url(url)
        self._username = username
        self._password = password
        self._csrf: str | None = None
        self._authenticated = False
        self._lock = asyncio.Lock()

    async def _request(
        self, method: str, path: str, body: dict | None = None, *, csrf: bool = False
    ) -> Any:
        headers = {
            "Accept": "application/json",
            "Origin": self.url,
            "Referer": self.url + "/userapp/",
        }
        if csrf:
            if not self._csrf:
                raise ModeError("The portal did not provide a CSRF token. No update was sent.")
            headers["X-CSRF-TOKEN"] = self._csrf
        try:
            async with self.session.request(
                method,
                self.url + "/userapp/api" + path,
                json=body,
                headers=headers,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status >= 300:
                    raise _HTTPError(response.status)
                if token := response.headers.get("X-CSRF-TOKEN"):
                    self._csrf = token
                raw = await response.read()
                if not raw:
                    return None
                try:
                    return await response.json()
                except ValueError, aiohttp.ContentTypeError, UnicodeError:
                    raise CannotConnect("The portal returned an unexpected response.") from None
        except aiohttp.ClientError, TimeoutError:
            if method == "PUT":
                raise ModeError(
                    "The update's outcome is unknown. Refresh charger status before retrying."
                ) from None
            raise CannotConnect("Cannot connect to the Charge Amps portal.") from None

    async def _login(self) -> None:
        self._authenticated = False
        self._csrf = None
        self.session.cookie_jar.clear()
        try:
            await self._request(
                "POST", "/auth/login", {"email": self._username, "password": self._password}
            )
        except _HTTPError as err:
            if err.status in (400, 401, 403):
                raise AuthenticationError("The portal rejected the username or password.") from None
            raise CannotConnect(str(err)) from None
        # The portal clears scoped-access/context cookies with an empty value and
        # a Unix-epoch expiry. aiohttp 3.14 can retain those deletion cookies,
        # causing the portal to reject a normal session as ended scoped access.
        self.session.cookie_jar.clear(lambda cookie: not cookie.value)
        self._authenticated = True

    async def _read(self, path: str) -> Any:
        if not self._authenticated:
            await self._login()
        for attempt in range(2):
            try:
                return await self._request("GET", path)
            except _HTTPError as err:
                if err.status == 401:
                    if attempt == 0:
                        await self._login()
                        continue
                    self._authenticated = False
                    raise AuthenticationError(
                        "The portal session was rejected. Sign in again."
                    ) from None
                raise CannotConnect(str(err)) from None
        raise CannotConnect("Cannot read charger status.")

    async def _raw_chargers(self) -> list[dict]:
        raw = await self._read("/users/chargepoints/owned?expand=ocppConfig,topChargingLimitation")
        parse_chargers(raw)
        return raw

    async def async_get_chargers(self) -> dict[str, Charger]:
        """Return status with no account or network secrets."""
        async with self._lock:
            return parse_chargers(await self._raw_chargers())

    async def async_set_mode(
        self, charger_id: str, connector_id: int, mode: str
    ) -> dict[str, Charger]:
        """Apply a mode and return its confirmed reported state."""
        if mode not in MODE_TO_PORTAL:
            raise ModeError("Choose Off, Schedule, or Always on.")
        async with self._lock:
            raw = await self._raw_chargers()  # Fresh payload, never cached across polls.
            matches = [item for item in raw if item["id"] == charger_id]
            if not matches:
                raise ModeError("The charger is no longer available to this account.")
            charger = matches[0]
            if charger.get("ownerReadOnly") or charger.get("ocppEnabled"):
                raise ModeError("The portal does not allow mode changes for this charger.")
            if charger.get("chargePointStatus") == "Offline":
                raise ModeError("The charger is offline.")
            connectors = [c for c in charger["connectors"] if c["connectorId"] == connector_id]
            if not connectors:
                raise ModeError("The selected connector no longer exists.")
            requested = MODE_TO_PORTAL[mode]
            if connectors[0].get("mode") == requested:
                return parse_chargers(raw)
            if mode == "Schedule":
                schedules = await self._read(
                    f"/smartChargingSchedules/chargepoint/{quote(charger_id, safe='')}"
                )
                if not isinstance(schedules, list) or not all(
                    isinstance(s, dict) for s in schedules
                ):
                    raise ModeError("The portal returned an unexpected schedule response.")
                if not any(s.get("connectorId") == connector_id for s in schedules):
                    raise ModeError(
                        "Create a schedule for this connector in the Charge Amps portal first."
                    )
            payload = deepcopy(charger)
            for connector in payload["connectors"]:
                if connector["connectorId"] == connector_id:
                    connector["mode"] = requested
            # Login is CSRF-exempt; setting mode requires the portal handshake.
            for attempt in range(2):
                if not self._csrf:
                    await self._read("/csrf/handshake")
                try:
                    await self._request("PUT", "/chargepoints", payload, csrf=True)
                    break
                except _HTTPError as err:
                    if attempt == 0 and err.status in (400, 403):
                        self._csrf = None
                        continue
                    if err.status == 401:
                        self._authenticated = False
                        raise AuthenticationError(
                            "The portal session expired. Refresh and try again."
                        ) from None
                    raise ModeError(str(err)) from None
            for attempt in range(5):
                updated = parse_chargers(await self._raw_chargers())
                current = updated.get(charger_id)
                if current and any(
                    c.id == connector_id and c.mode == mode for c in current.connectors
                ):
                    return updated
                if attempt < 4:
                    await asyncio.sleep(1)
            raise ModeError(
                "The update was accepted but is not yet confirmed. Refresh before retrying."
            )
