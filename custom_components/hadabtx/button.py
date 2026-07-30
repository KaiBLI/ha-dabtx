"""The Apply Changes button. This is the only entity in this integration
that actually writes to the modulator -- it reads whatever has been staged
in the number/select/text entities, applies it in one combined
read-modify-write-restart cycle, then clears the staged block/frequency
choice (amplitude/DAC current/remote IP/port stay staged as a convenience,
since it's common to leave them as-is and only change frequency next time)."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import DabModulatorError
from .const import DOMAIN
from .coordinator import DabModulatorCoordinator
from .models import PendingConfig


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entry_data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DabApplyButton(entry, entry_data)])


class DabApplyButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "apply_changes"

    def __init__(self, entry: ConfigEntry, entry_data: dict) -> None:
        self._entry = entry
        self._entry_data = entry_data
        self._attr_unique_id = f"{entry.entry_id}_apply_changes"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    async def async_press(self) -> None:
        pending: PendingConfig = self._entry_data["pending"]
        coordinator: DabModulatorCoordinator = self._entry_data["coordinator"]

        kwargs = pending.as_kwargs()
        if not kwargs:
            raise HomeAssistantError(
                "No pending changes are staged -- set a value on one of the "
                "config entities first, then press Apply Changes."
            )

        try:
            await coordinator.client.async_apply_changes(**kwargs)
        except DabModulatorError as err:
            raise HomeAssistantError(str(err)) from err

        await coordinator.async_request_refresh()
