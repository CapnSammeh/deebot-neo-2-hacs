"""Constants for the DEEBOT NEO 2 integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "deebot_neo_2"
NAME = "DEEBOT NEO 2"
VERSION = "0.2.0"

SUPPORTED_DEVICE_CLASS = "q287s6"
SUPPORTED_DEVICE_CLASSES = {"q287s6", "eyfj07"}
SUPPORTED_MODELS = {"DEEBOT NEO 2.0", "DEEBOT NEO 2.0 PLUS"}

CONF_DEVICE_DID = "device_did"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_RESOURCE = "device_resource"
CONF_VERIFICATION_CODE = "verification_code"

PLATFORMS: tuple[Platform, ...] = (
    Platform.VACUUM,
    Platform.SENSOR,
    Platform.BUTTON,
)

SUCTION_OPTIONS = ["quiet mode", "standard", "strong", "max"]
