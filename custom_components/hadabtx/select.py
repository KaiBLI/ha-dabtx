"""Staging select entity for picking a DAB block (e.g. 9B) instead of a raw
Hz value. Does NOT write to the modulator on change -- see number.py."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DAB_BLOCKS, DOMAIN
from .models import PendingConfig

UNSET = "(unchanged)"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    pending: PendingConfig = hass.data[DOMAIN][entry.entry_id]["pending"]
    async_add_entities([DabBlockSelect(entry, pending), DabConnectionModeSelect(entry, pending)])

class DabBlockSelect(SelectEntity, RestoreEntity):
    """
    Setting this clears any staged exact frequency, since only one of
    dab_block/frequency_hz can apply.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "dab_block_set"

    def __init__(self, entry: ConfigEntry, pending: PendingConfig) -> None:
        self._entry = entry
        self._pending = pending
        self._attr_unique_id = f"{entry.entry_id}_pending_dab_block"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})
        self._attr_options = [UNSET] + sorted(DAB_BLOCKS)
        self._attr_current_option = UNSET

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state in self._attr_options:
            self._attr_current_option = last_state.state
            self._pending.dab_block = None if last_state.state == UNSET else last_state.state

    async def async_select_option(self, option: str) -> None:
        self._attr_current_option = option
        self._pending.dab_block = None if option == UNSET else option
        if option != UNSET:
            self._pending.frequency_hz = None
        self.async_write_ha_state()

class DabConnectionModeSelect(SelectEntity, RestoreEntity):
    """
    Stages the TCP server/client/off mode (flash config byte). Needed if
    you want the ETI socket switch's "on" path to work -- turning the
    socket on requires the device already be configured as server or
    client, since that determines which live-action endpoint to call.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "connection_mode_set"

    def __init__(self, entry: ConfigEntry, pending: PendingConfig) -> None:
        self._entry = entry
        self._pending = pending
        self._attr_unique_id = f"{entry.entry_id}_pending_connection_mode"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})
        self._attr_options = [UNSET, "server", "client", "off"]
        self._attr_current_option = UNSET

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state in self._attr_options:
            self._attr_current_option = last_state.state
            self._pending.connection_mode = None if last_state.state == UNSET else last_state.state

    async def async_select_option(self, option: str) -> None:
        self._attr_current_option = option
        self._pending.connection_mode = None if option == UNSET else option
        self.async_write_ha_state()