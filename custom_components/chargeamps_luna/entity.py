"""Common device and coordinator entity behavior."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Charger, Connector
from .const import DOMAIN
from .coordinator import ChargeAmpsCoordinator


class ChargeAmpsEntity(CoordinatorEntity[ChargeAmpsCoordinator]):
    """An entity on a charger, optionally on one of its connectors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ChargeAmpsCoordinator,
        charger: Charger,
        key: str,
        connector_id: int | None = None,
    ):
        super().__init__(coordinator)
        self.charger_id = charger.id
        self.connector_id = connector_id
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{charger.id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.config_entry.entry_id}_{charger.id}")},
            name=charger.name,
            manufacturer="Charge Amps",
            model=charger.model,
            sw_version=charger.firmware,
            serial_number=charger.id,
            configuration_url=coordinator.client.url + "/userapp/",
        )

    @property
    def charger(self) -> Charger | None:
        return self.coordinator.data.get(self.charger_id)

    @property
    def connector(self) -> Connector | None:
        charger = self.charger
        if charger:
            return next((c for c in charger.connectors if c.id == self.connector_id), None)
        return None

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.charger is not None
            and (self.connector_id is None or self.connector is not None)
        )


def connector_name(connector_id: int, label: str, count: int) -> str:
    return label if count == 1 else f"Connector {connector_id} {label.lower()}"
