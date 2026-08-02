"""Binary sensors for boolean status flags."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DabModulatorCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: DabModulatorCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        [
            DabSramDetectedBinarySensor(coordinator, entry),
            DabBroadcastingBinarySensor(coordinator, entry),
        ]
    )


class _DabModulatorBinarySensorBase(CoordinatorEntity[DabModulatorCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _key = "base"
    _data_key = "base"

    def __init__(self, coordinator: DabModulatorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})
        self._attr_unique_id = f"{entry.entry_id}_{self._key}"

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._data_key)


class DabSramDetectedBinarySensor(_DabModulatorBinarySensorBase):
    _key = "sram_detected"
    _data_key = "sram_detected"
    _attr_translation_key = "sram_detected"


class DabBroadcastingBinarySensor(_DabModulatorBinarySensorBase):
    _key = "broadcasting"
    _data_key = "broadcasting"
    _attr_translation_key = "broadcasting"
    _attr_device_class = BinarySensorDeviceClass.RUNNING