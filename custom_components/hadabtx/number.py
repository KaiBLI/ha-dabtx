"""Staging number entities. These do NOT write to the modulator on change --
they hold a value locally until the Apply Changes button is pressed."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
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
    async_add_entities(
        [
            DabAmplitudeNumber(entry, pending),
            DabDacCurrentNumber(entry, pending),
            DabRemotePortNumber(entry, pending),
            DabFrequencyNumber(entry, pending),
            DabTiiMainIdNumber(entry, pending),
            DabTiiSubIdNumber(entry, pending),
        ]
    )


class _PendingNumberBase(NumberEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX
    _field: str = ""
    _min: float = 0
    _max: float = 255
    _step: float = 1
    _is_float = False

    def __init__(self, entry: ConfigEntry, pending: PendingConfig) -> None:
        self._entry = entry
        self._pending = pending
        self._attr_unique_id = f"{entry.entry_id}_pending_{self._field}"
        self._attr_native_min_value = self._min
        self._attr_native_max_value = self._max
        self._attr_native_step = self._step
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            try:
                value = float(last_state.state)
            except ValueError:
                return
            self._attr_native_value = value
            setattr(self._pending, self._field, value if self._is_float else int(value))

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        setattr(self._pending, self._field, value if self._is_float else int(value))
        self.async_write_ha_state()


class DabAmplitudeNumber(_PendingNumberBase):
    _field = "amplitude"
    _attr_translation_key = "amplitude_set"
    _min, _max, _step = 0, 255, 1


class DabDacCurrentNumber(_PendingNumberBase):
    _field = "dac_current"
    _attr_translation_key = "dac_current_set"
    _min, _max, _step = 0, 255, 1


class DabRemotePortNumber(_PendingNumberBase):
    _field = "remote_port"
    _attr_translation_key = "remote_port_set"
    _min, _max, _step = 0, 65535, 1


class DabFrequencyNumber(_PendingNumberBase):
    """
    Exact frequency in Hz, for cases the DAB block dropdown doesn't cover.
    Setting this clears any staged DAB block, since only one can apply.
    """

    _field = "frequency_hz"
    _attr_translation_key = "frequency_set"
    _min, _max, _step = 170000000, 240000000, 16000  # DAB channel raster
    _is_float = True

    async def async_set_native_value(self, value: float) -> None:
        await super().async_set_native_value(value)
        self._pending.dab_block = None

class DabTiiMainIdNumber(_PendingNumberBase):
    """0-69, per the device's tiiPat lookup table -- NOT the 0-69 range
    someone might guess applies to both TII fields; Sub Id below has a
    different, narrower range."""

    _field = "tii_main_id"
    _attr_translation_key = "tii_main_id_set"
    _min, _max, _step = 0, 69, 1

class DabTiiSubIdNumber(_PendingNumberBase):
    """0-23 -- masked to 5 bits on write by the device itself."""

    _field = "tii_sub_id"
    _attr_translation_key = "tii_sub_id_set"
    _min, _max, _step = 0, 23, 1