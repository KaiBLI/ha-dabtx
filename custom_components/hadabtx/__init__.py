"""The odrDAB TX Integration."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DabModulatorClient, DabModulatorError
from .const import (
    ATTR_AMPLITUDE,
    ATTR_CONNECTION_MODE,
    ATTR_DAB_BLOCK,
    ATTR_DAC_CURRENT,
    ATTR_FREQUENCY_HZ,
    ATTR_REMOTE_IP,
    ATTR_REMOTE_PORT,
    DAB_BLOCKS,
    DOMAIN,
    SERVICE_SET_CONFIG,
    ATTR_TII_MAIN_ID,
    ATTR_TII_SUB_ID,
)
from .coordinator import DabModulatorCoordinator
from .models import PendingConfig

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.TEXT,
    Platform.BUTTON,
    Platform.SWITCH,
]

SET_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Optional(ATTR_REMOTE_IP): cv.string,
        vol.Optional(ATTR_REMOTE_PORT): vol.All(vol.Coerce(int), vol.Range(min=0, max=65535)),
        vol.Optional(ATTR_FREQUENCY_HZ): vol.Coerce(float),
        vol.Optional(ATTR_DAB_BLOCK): vol.In(sorted(DAB_BLOCKS)),
        vol.Optional(ATTR_AMPLITUDE): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
        vol.Optional(ATTR_DAC_CURRENT): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
        vol.Optional(ATTR_CONNECTION_MODE): vol.In(["server", "client", "off"]),
        vol.Optional(ATTR_TII_MAIN_ID): vol.All(vol.Coerce(int), vol.Range(min=0, max=69)),
        vol.Optional(ATTR_TII_SUB_ID): vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    client = DabModulatorClient(
        session,
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    coordinator = DabModulatorCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "pending": PendingConfig(),
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _async_register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_SET_CONFIG)
    return unload_ok


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SET_CONFIG):
        return

    async def async_handle_set_config(call: ServiceCall) -> None:
        device_id = call.data["device_id"]
        device_registry = dr.async_get(hass)
        device = device_registry.async_get(device_id)
        if device is None:
            raise HomeAssistantError(f"Unknown device_id: {device_id}")

        entry_id = next(iter(device.config_entries), None)
        entry_data = hass.data.get(DOMAIN, {}).get(entry_id)
        if entry_data is None:
            raise HomeAssistantError(f"No odrDAB TX Integration config entry found for device {device_id}")
        coordinator: DabModulatorCoordinator = entry_data["coordinator"]

        kwargs = {
            k: call.data[k]
            for k in (
                ATTR_REMOTE_IP,
                ATTR_REMOTE_PORT,
                ATTR_FREQUENCY_HZ,
                ATTR_DAB_BLOCK,
                ATTR_AMPLITUDE,
                ATTR_DAC_CURRENT,
                ATTR_CONNECTION_MODE,
                ATTR_TII_MAIN_ID,
                ATTR_TII_SUB_ID,
            )
            if k in call.data
        }

        try:
            await coordinator.client.async_apply_changes(**kwargs)
        except DabModulatorError as err:
            raise HomeAssistantError(str(err)) from err

        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN, SERVICE_SET_CONFIG, async_handle_set_config, schema=SET_CONFIG_SCHEMA
    )
