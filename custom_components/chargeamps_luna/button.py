"""Refresh charger status immediately."""

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ChargeAmpsConfigEntry
from .entity import ChargeAmpsEntity

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
            if charger.id not in known:
                known.add(charger.id)
                entities.append(ChargeAmpsRefreshButton(coordinator, charger, "refresh"))
        async_add_entities(entities)

    add_entities()
    entry.async_on_unload(coordinator.async_add_listener(add_entities))


class ChargeAmpsRefreshButton(ChargeAmpsEntity, ButtonEntity):
    _attr_name = "Refresh status"
    _attr_device_class = ButtonDeviceClass.UPDATE

    @property
    def available(self) -> bool:
        # Allow recovery after a failed automatic poll.
        return True

    async def async_press(self) -> None:
        await self.coordinator.async_refresh_status()
