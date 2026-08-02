"""Live toggle switches. Unlike the flash config writes, these are
one-shot action requests -- no erase/write/reboot involved, so they take
effect immediately."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import DabModulatorError
from .const import DOMAIN
from .coordinator import DabModulatorCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: DabModulatorCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        [
            DabRfFrontendSwitch(coordinator, entry),
            DabEtiSocketSwitch(coordinator, entry),
        ]
    )


class _DabModulatorSwitchBase(CoordinatorEntity[DabModulatorCoordinator], SwitchEntity):
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


class DabRfFrontendSwitch(_DabModulatorSwitchBase):
    _key = "rf_frontend_switch"
    _data_key = "rf_frontend_active"
    _attr_translation_key = "rf_frontend_switch"

    async def async_turn_on(self, **kwargs) -> None:
        try:
            await self.coordinator.client.async_set_rf_frontend(True)
        except DabModulatorError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        try:
            await self.coordinator.client.async_set_rf_frontend(False)
        except DabModulatorError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()


class DabEtiSocketSwitch(_DabModulatorSwitchBase):
    _key = "eti_socket_switch"
    _data_key = "eti_socket_on"
    _attr_translation_key = "eti_socket_switch"

    async def async_turn_on(self, **kwargs) -> None:
        try:
            await self.coordinator.client.async_set_eti_socket(True)
        except DabModulatorError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        try:
            await self.coordinator.client.async_set_eti_socket(False)
        except DabModulatorError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()