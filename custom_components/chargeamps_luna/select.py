"""Off, Schedule, and Always on charging mode."""

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import MODE_TO_PORTAL
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
                    entity = ChargeAmpsModeSelect(
                        coordinator, charger, f"connector_{connector.id}_mode", connector.id
                    )
                    entity._attr_name = connector_name(
                        connector.id, "Charging mode", len(charger.connectors)
                    )
                    entities.append(entity)
        async_add_entities(entities)

    add_entities()
    entry.async_on_unload(coordinator.async_add_listener(add_entities))


class ChargeAmpsModeSelect(ChargeAmpsEntity, SelectEntity):
    _attr_options = list(MODE_TO_PORTAL)
    _attr_icon = "mdi:ev-station"

    @property
    def current_option(self) -> str | None:
        return self.connector.mode if self.connector else None

    @property
    def available(self) -> bool:
        return (
            super().available
            and not self.charger.read_only
            and not self.charger.externally_managed
            and self.charger.status != "Offline"
        )

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_mode(self.charger_id, self.connector_id, option)
