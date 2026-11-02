"""Whether the charger is currently charging."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
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
    known_chargers = set()

    @callback
    def add_entities() -> None:
        entities = []
        for charger in coordinator.data.values():
            if charger.id not in known_chargers:
                known_chargers.add(charger.id)
                entities.append(
                    ChargeAmpsPortalConnection(coordinator, charger, "portal_connection")
                )
            for connector in charger.connectors:
                if (charger.id, connector.id) not in known:
                    known.add((charger.id, connector.id))
                    entity = ChargeAmpsChargingSensor(
                        coordinator, charger, f"connector_{connector.id}_charging", connector.id
                    )
                    entity._attr_name = connector_name(
                        connector.id, "Charging", len(charger.connectors)
                    )
                    entities.append(entity)
                    fault = ChargeAmpsFaultSensor(
                        coordinator, charger, f"connector_{connector.id}_fault", connector.id
                    )
                    fault._attr_name = connector_name(
                        connector.id, "Fault", len(charger.connectors)
                    )
                    entities.append(fault)
        async_add_entities(entities)

    add_entities()
    entry.async_on_unload(coordinator.async_add_listener(add_entities))


class ChargeAmpsChargingSensor(ChargeAmpsEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    @property
    def is_on(self) -> bool | None:
        return self.connector.is_charging if self.connector else None

    @property
    def available(self) -> bool:
        return super().available and self.charger.status != "Offline"


class ChargeAmpsPortalConnection(ChargeAmpsEntity, BinarySensorEntity):
    """Whether Home Assistant's most recent portal request succeeded."""

    _attr_name = "Portal connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict:
        return {"last_error": self.coordinator.refresh_error}


class ChargeAmpsFaultSensor(ChargeAmpsEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool | None:
        if connector := self.connector:
            if connector.status == "Faulted" or connector.error_code not in (None, "", "NoError"):
                return True
            if connector.error_code == "NoError" or connector.status not in (None, "Unknown"):
                return False
        return None

    @property
    def available(self) -> bool:
        return super().available and self.charger.status != "Offline"
