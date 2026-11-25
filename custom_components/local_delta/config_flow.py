"""Config flow: the faucet is identified by its Wi-Fi MAC."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback

from .const import CONF_DEVICE_ID, CONF_PRESENCE_TOPIC, DEFAULT_PRESENCE_TOPIC, DOMAIN
from .protocol import normalize_device_id


class LocalDeltaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a faucet."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                device_id = normalize_device_id(user_input[CONF_DEVICE_ID])
            except ValueError:
                errors[CONF_DEVICE_ID] = "invalid_device_id"
            else:
                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={CONF_DEVICE_ID: device_id},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default="Kitchen faucet"): str,
                    vol.Required(CONF_DEVICE_ID): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return LocalDeltaOptionsFlow()


class LocalDeltaOptionsFlow(OptionsFlow):
    """Change the broker presence topic, or clear it if the broker has none."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_PRESENCE_TOPIC: user_input.get(CONF_PRESENCE_TOPIC, "")}
            )
        current = self.config_entry.options.get(
            CONF_PRESENCE_TOPIC,
            DEFAULT_PRESENCE_TOPIC.format(device_id=self.config_entry.data[CONF_DEVICE_ID]),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Optional(CONF_PRESENCE_TOPIC, description={"suggested_value": current}): str}
            ),
        )
