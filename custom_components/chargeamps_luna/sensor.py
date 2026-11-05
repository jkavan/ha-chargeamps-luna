"""Charger connectivity and connector status."""

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ChargeAmpsConfigEntry
from .entity import ChargeAmpsEntity, connector_name

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ChargeAmpsConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    known = set()

    @callback
    def add_entities() -> None:
        entities = []
        for charger in coordinator.data.values():
            if (charger.id, None) not in known:
                known.add((charger.id, None))
                entities.append(ChargeAmpsStatusSensor(coordinator, charger, "status"))
                entities.extend(
                    [
                        ChargeAmpsRefreshSensor(coordinator, charger, "last_successful_refresh"),
                        ChargeAmpsFirmwareSensor(coordinator, charger, "firmware"),
                    ]
                )
            for connector in charger.connectors:
                if (charger.id, connector.id) not in known:
                    known.add((charger.id, connector.id))
                    entity = ChargeAmpsStatusSensor(
                        coordinator, charger, f"connector_{connector.id}_status", connector.id
                    )
                    entity._attr_name = connector_name(
                        connector.id, "Connector status", len(charger.connectors)
                    )
                    entities.append(entity)
                    error = ChargeAmpsErrorSensor(
                        coordinator, charger, f"connector_{connector.id}_error_code", connector.id
                    )
                    error._attr_name = connector_name(
                        connector.id, "Error code", len(charger.connectors)
                    )
                    entities.append(error)
                    energy = ChargeAmpsSessionEnergySensor(
                        coordinator,
                        charger,
                        f"connector_{connector.id}_session_energy",
                        connector.id,
                    )
                    energy._attr_name = connector_name(
                        connector.id, "Session energy", len(charger.connectors)
                    )
                    entities.append(energy)
                    total = ChargeAmpsTotalEnergySensor(
                        coordinator, charger, f"connector_{connector.id}_total_energy", connector.id
                    )
                    total._attr_name = connector_name(
                        connector.id, "Total energy", len(charger.connectors)
                    )
                    entities.append(total)
        async_add_entities(entities)

    add_entities()
    entry.async_on_unload(coordinator.async_add_listener(add_entities))


class ChargeAmpsStatusSensor(ChargeAmpsEntity, SensorEntity):
    _attr_name = "Status"
    _attr_icon = "mdi:ev-station"

    @property
    def native_value(self) -> str | None:
        if self.connector_id is not None:
            return self.connector.status if self.connector else None
        return self.charger.status if self.charger else None

    @property
    def extra_state_attributes(self) -> dict | None:
        if self.connector:
            return {"error_code": self.connector.error_code}
        return None


class ChargeAmpsRefreshSensor(ChargeAmpsEntity, SensorEntity):
    """Keep the last successful fetch visible during a connection failure."""

    _attr_name = "Last successful refresh"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.last_update_success_time


class ChargeAmpsFirmwareSensor(ChargeAmpsEntity, SensorEntity):
    _attr_name = "Firmware"
    _attr_icon = "mdi:chip"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str | None:
        return self.charger.firmware if self.charger else None

    @property
    def extra_state_attributes(self) -> dict | None:
        if charger := self.charger:
            return {"available_version": charger.available_firmware}
        return None


class ChargeAmpsErrorSensor(ChargeAmpsEntity, SensorEntity):
    _attr_icon = "mdi:alert-circle-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str | None:
        return self.connector.error_code if self.connector else None


class ChargeAmpsSessionEnergySensor(ChargeAmpsEntity, SensorEntity):
    """Reported session energy; never accumulate these resetting snapshots."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 3

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None

    @property
    def native_value(self) -> float | None:
        if connector := self.connector:
            return connector.session_energy_kwh
        return None


class ChargeAmpsTotalEnergySensor(ChargeAmpsEntity, SensorEntity):
    """The charger's precise lifetime energy meter, suitable for energy statistics."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL
    _attr_suggested_display_precision = 3

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None

    @property
    def native_value(self) -> float | None:
        return self.connector.total_energy_kwh if self.connector else None

    @property
    def extra_state_attributes(self) -> dict | None:
        if connector := self.connector:
            return {"last_meter_sample": connector.energy_sampled_at}
        return None
