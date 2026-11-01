"""Whether the charger is currently charging."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant, callback
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
