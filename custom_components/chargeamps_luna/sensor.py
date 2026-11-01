"""Charger connectivity and connector status."""

from homeassistant.components.sensor import SensorEntity
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
            if (charger.id, None) not in known:
                known.add((charger.id, None))
                entities.append(ChargeAmpsStatusSensor(coordinator, charger, "status"))
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
