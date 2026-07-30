"""Sensor platform for the odrDAB TX Integration."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
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
            DabFrequencySensor(coordinator, entry),
            DabBlockSensor(coordinator, entry),
            DabAmplitudeSensor(coordinator, entry),
            DabDacCurrentSensor(coordinator, entry),
            DabRemoteIpSensor(coordinator, entry),
            DabRemotePortSensor(coordinator, entry),
        ]
    )


class _DabModulatorSensorBase(CoordinatorEntity[DabModulatorCoordinator], SensorEntity):
    """Common device info for all sensors of one modulator."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DabModulatorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="odrDAB TX Integration",
        )
        self._attr_unique_id = f"{entry.entry_id}_{self._key}"

    _key = "base"


class DabFrequencySensor(_DabModulatorSensorBase):
    _key = "frequency"
    _attr_translation_key = "frequency"
    _attr_native_unit_of_measurement = "Hz"

    @property
    def native_value(self):
        return self.coordinator.data.get("frequency_hz") if self.coordinator.data else None


class DabBlockSensor(_DabModulatorSensorBase):
    _key = "dab_block"
    _attr_translation_key = "dab_block"

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("dab_block") or "Unknown"


class DabAmplitudeSensor(_DabModulatorSensorBase):
    _key = "amplitude"
    _attr_translation_key = "amplitude"

    @property
    def native_value(self):
        return self.coordinator.data.get("amplitude") if self.coordinator.data else None


class DabDacCurrentSensor(_DabModulatorSensorBase):
    _key = "dac_current"
    _attr_translation_key = "dac_current"

    @property
    def native_value(self):
        return self.coordinator.data.get("dac_current") if self.coordinator.data else None


class DabRemoteIpSensor(_DabModulatorSensorBase):
    _key = "remote_ip"
    _attr_translation_key = "remote_ip"

    @property
    def native_value(self):
        return self.coordinator.data.get("remote_ip") if self.coordinator.data else None


class DabRemotePortSensor(_DabModulatorSensorBase):
    _key = "remote_port"
    _attr_translation_key = "remote_port"

    @property
    def native_value(self):
        return self.coordinator.data.get("remote_port") if self.coordinator.data else None
