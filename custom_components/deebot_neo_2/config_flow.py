"""Config flow for the DEEBOT NEO 2 integration."""

from __future__ import annotations

import logging
import random
import string
from typing import Any

from deebot_client.api_client import ApiClient
from deebot_client.authentication import Authenticator, create_rest_config
from deebot_client.exceptions import (
    DeviceVerificationRequiredError,
    InvalidAuthenticationError,
    InvalidVerificationCodeError,
)
from deebot_client.util import md5
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_COUNTRY, CONF_PASSWORD, CONF_USERNAME
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import aiohttp_client, selector

from . import _patch_deebot_client
from .const import (
    CONF_DEVICE_DID,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_RESOURCE,
    CONF_VERIFICATION_CODE,
    DOMAIN,
    SUPPORTED_DEVICE_CLASS,
)

_LOGGER = logging.getLogger(__name__)

NEO_2_LOGIC_ID = "y30plus_ww_h_y30h5"


def _device_label(info: dict[str, Any]) -> str:
    return str(info.get("nick") or info.get("deviceName") or info.get("name") or info["did"])


def _device_api_info(device: Any) -> dict[str, Any]:
    return device.api if hasattr(device, "api") else device


def _is_supported_neo_2(info: dict[str, Any]) -> bool:
    device_name = str(info.get("deviceName") or "")
    return (
        info.get("class") == SUPPORTED_DEVICE_CLASS
        or "NEO 2.0" in device_name
        or info.get("UILogicId") == NEO_2_LOGIC_ID
    )


def _generate_device_id() -> str:
    """Generate a random client device ID for Ecovacs."""
    return "".join(
        random.choice(string.ascii_uppercase + string.digits) for _ in range(8)
    )


class DeebotNeo2ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DEEBOT NEO 2."""

    VERSION = 1

    def __init__(self) -> None:
        self._auth_input: dict[str, Any] = {}
        self._devices: list[dict[str, Any]] = []
        self._device_id: str = ""
        self._authenticator: Authenticator | None = None

    async def _async_teardown_authenticator(self) -> None:
        """Tear down the authenticator to cancel its token refresh timer."""
        if self._authenticator is not None:
            await self._authenticator.teardown()
            self._authenticator = None

    async def _async_create_authenticator(
        self, user_input: dict[str, Any]
    ) -> Authenticator:
        """Create an Authenticator with a stable client device ID."""
        await self._async_teardown_authenticator()
        if not self._device_id:
            self._device_id = _generate_device_id()
        self._authenticator = Authenticator(
            create_rest_config(
                aiohttp_client.async_get_clientsession(self.hass),
                device_id=self._device_id,
                alpha_2_country=user_input[CONF_COUNTRY],
            ),
            user_input[CONF_USERNAME],
            md5(user_input[CONF_PASSWORD]),
        )
        return self._authenticator

    async def _async_authenticate_and_discover(
        self, authenticator: Authenticator
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        """Authenticate and discover supported q287s6 devices."""
        errors: dict[str, str] = {}
        try:
            await authenticator.authenticate()
        except DeviceVerificationRequiredError:
            # Handled by the caller, which starts the verification step
            raise
        except InvalidAuthenticationError:
            _LOGGER.debug("Invalid Ecovacs authentication details", exc_info=True)
            errors["base"] = "invalid_auth"
            return [], errors
        except Exception:
            _LOGGER.exception("Unexpected exception during Ecovacs authentication")
            errors["base"] = "unknown"
            return [], errors

        api_client = ApiClient(authenticator)
        try:
            _patch_deebot_client()
            devices = await api_client.get_devices()
        except ConfigEntryNotReady:
            _LOGGER.debug("Cannot connect to Ecovacs during device discovery", exc_info=True)
            errors["base"] = "cannot_connect"
            return [], errors
        except ConfigEntryError:
            _LOGGER.debug("Invalid Ecovacs auth during device discovery", exc_info=True)
            errors["base"] = "invalid_auth"
            return [], errors
        except Exception:
            _LOGGER.exception("Unexpected exception during DEEBOT NEO 2 setup")
            errors["base"] = "unknown"
            return [], errors

        discovered = [_device_api_info(device) for device in devices.mqtt] + devices.not_supported
        for info in discovered:
            _LOGGER.debug(
                "Ecovacs discovery saw device class=%s deviceName=%s",
                info.get("class"),
                info.get("deviceName"),
            )

        supported = [info for info in discovered if _is_supported_neo_2(info)]
        if not supported:
            errors["base"] = "no_supported_vacuums"
        return supported, errors

    async def _async_request_verification_code(self) -> dict[str, str]:
        """Request a device verification code from Ecovacs."""
        if not self._authenticator:
            return {"base": "unknown"}
        try:
            await self._authenticator.request_device_verification_code()
        except Exception:
            _LOGGER.exception("Failed to request verification code")
            return {"base": "cannot_connect"}
        return {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle Ecovacs account details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._auth_input = {}
            self._devices = []
            authenticator = await self._async_create_authenticator(user_input)
            try:
                devices, errors = await self._async_authenticate_and_discover(
                    authenticator
                )
            except DeviceVerificationRequiredError:
                errors = await self._async_request_verification_code()
                if not errors:
                    self._auth_input = user_input
                    return await self.async_step_device_verification()
                # If requesting code failed, fall through to show auth form with error

            if not errors:
                self._auth_input = user_input
                self._devices = devices
                if len(devices) == 1:
                    return await self._create_entry(devices[0])
                return await self.async_step_select_device()

        defaults = dict(user_input or {CONF_COUNTRY: self.hass.config.country})
        if errors:
            defaults.pop(CONF_PASSWORD, None)
        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
                vol.Required(CONF_PASSWORD): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Required(CONF_COUNTRY): selector.CountrySelector(),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, defaults),
            errors=errors,
        )

    async def async_step_device_verification(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Verify the Ecovacs client device ID via email code."""
        errors: dict[str, str] = {}
        if user_input and self._authenticator:
            try:
                await self._authenticator.verify_device(
                    user_input[CONF_VERIFICATION_CODE]
                )
            except InvalidVerificationCodeError:
                errors["base"] = "invalid_verification_code"
            except Exception:
                _LOGGER.exception("Unexpected exception verifying Ecovacs device")
                errors["base"] = "unknown"
            else:
                # Verification succeeded — now authenticate and discover devices
                try:
                    devices, discover_errors = (
                        await self._async_authenticate_and_discover(
                            self._authenticator
                        )
                    )
                except DeviceVerificationRequiredError:
                    # Should not happen after successful verification, but handle it
                    errors["base"] = "device_verification_required"
                    return self.async_show_form(
                        step_id="device_verification",
                        data_schema=vol.Schema(
                            {
                                vol.Required(CONF_VERIFICATION_CODE): selector.TextSelector(
                                    selector.TextSelectorConfig(
                                        type=selector.TextSelectorType.TEXT
                                    )
                                )
                            }
                        ),
                        description_placeholders={
                            CONF_USERNAME: self._auth_input.get(CONF_USERNAME, ""),
                        },
                        errors=errors,
                    )

                if discover_errors:
                    errors.update(discover_errors)
                else:
                    self._devices = devices
                    if len(devices) == 1:
                        return await self._create_entry(devices[0])
                    return await self.async_step_select_device()

        return self.async_show_form(
            step_id="device_verification",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_VERIFICATION_CODE): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEXT
                        )
                    )
                }
            ),
            description_placeholders={
                CONF_USERNAME: self._auth_input.get(CONF_USERNAME, ""),
            },
            errors=errors,
        )

    async def async_step_select_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user choose a q287s6 vacuum."""
        if user_input is not None:
            selected = next(
                device
                for device in self._devices
                if device["did"] == user_input[CONF_DEVICE_DID]
            )
            return await self._create_entry(selected)

        options = {device["did"]: _device_label(device) for device in self._devices}
        return self.async_show_form(
            step_id="select_device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_DID): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=value, label=label)
                                for value, label in options.items()
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def _create_entry(self, device: dict[str, Any]) -> ConfigFlowResult:
        await self.async_set_unique_id(device["did"])
        self._abort_if_unique_id_configured()
        data = dict(self._auth_input)
        data[CONF_DEVICE_ID] = self._device_id
        data[CONF_DEVICE_DID] = device["did"]
        data[CONF_DEVICE_RESOURCE] = device.get("resource")
        data[CONF_DEVICE_NAME] = _device_label(device)
        return self.async_create_entry(title=_device_label(device), data=data)
