"""Staging text entity for the remote/ETI server IP. Does NOT write to the
modulator on change -- see number.py."""
from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .models import PendingConfig


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    pending: PendingConfig = hass.data[DOMAIN][entry.entry_id]["pending"]
    async_add_entities([DabRemoteIpText(entry, pending)])


class DabRemoteIpText(TextEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "remote_ip_set"

    def __init__(self, entry: ConfigEntry, pending: PendingConfig) -> None:
        self._entry = entry
        self._pending = pending
        self._attr_unique_id = f"{entry.entry_id}_pending_remote_ip"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})
        self._attr_native_value = ""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            self._attr_native_value = last_state.state
            self._pending.remote_ip = last_state.state or None

    async def async_set_value(self, value: str) -> None:
        self._attr_native_value = value
        self._pending.remote_ip = value or None
        self.async_write_ha_state()
