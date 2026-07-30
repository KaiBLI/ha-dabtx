"""Data update coordinator for the odrDAB TX Integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DabModulatorClient, DabModulatorError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class DabModulatorCoordinator(DataUpdateCoordinator[dict]):
    """Polls a single modulator for status."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: DabModulatorClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({entry.data['host']})",
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.client = client
        self.entry = entry

    async def _async_update_data(self) -> dict:
        try:
            return await self.client.async_get_status()
        except DabModulatorError as err:
            raise UpdateFailed(str(err)) from err
