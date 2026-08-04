"""DEEBOT NEO 2 custom integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
import sys
from typing import Any

import deebot_client.hardware as deebot_hardware
from deebot_client.device import Device

from homeassistant.config_entries import ConfigEntry
from homeassistant.components.ecovacs.controller import EcovacsController
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from . import q287s6_app, q287s6_profile
from .const import CONF_DEVICE_DID, CONF_DEVICE_ID, DOMAIN, PLATFORMS, SUPPORTED_DEVICE_CLASSES

_LOGGER = logging.getLogger(__name__)


def _patch_deebot_client() -> None:
    """Expose q287s6 and eyfj07 support to deebot_client before devices initialize."""
    sys.modules.setdefault("deebot_client.commands.json.q287s6_app", q287s6_app)
    sys.modules.setdefault("deebot_client.hardware.q287s6", q287s6_profile)
    sys.modules.setdefault("deebot_client.commands.json.eyfj07_app", q287s6_app)
    sys.modules.setdefault("deebot_client.hardware.eyfj07", q287s6_profile)
    if not_found := getattr(deebot_hardware, "_NOT_FOUND", None):
        for cls in SUPPORTED_DEVICE_CLASSES:
            not_found.discard(cls)


class Neo2Controller(EcovacsController):
    """Official Ecovacs controller with q287s6 registration and filtering."""

    def __init__(self, hass: HomeAssistant, config: Mapping[str, Any]) -> None:
        super().__init__(hass, config)
        self._config = config

    async def initialize(self) -> None:
        """Register q287s6, then run the official Ecovacs controller setup."""
        _patch_deebot_client()
        await super().initialize()

        selected_did = self._config.get(CONF_DEVICE_DID)
        selected_devices: list[Device] = []
        for device in self._devices:
            if device.device_info.get("class") in SUPPORTED_DEVICE_CLASSES and (
                selected_did is None or device.device_info.get("did") == selected_did
            ):
                selected_devices.append(device)
            else:
                await device.teardown()

        self._devices = selected_devices
        if not self._devices:
            raise ConfigEntryNotReady("No selected q287s6 device found")

        _LOGGER.debug("Initialized %s q287s6 device(s)", len(self._devices))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DEEBOT NEO 2 from a config entry."""
    controller = Neo2Controller(hass, entry.data)
    await controller.initialize()
    entry.runtime_data = controller
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    controller: Neo2Controller = entry.runtime_data
    await controller.teardown()
    return unload_ok
