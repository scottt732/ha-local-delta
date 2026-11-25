"""Local Delta Faucet: control a Delta VoiceIQ faucet over a local MQTT broker."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_AMOUNT,
    ATTR_DEVICE_ID,
    ATTR_PAYLOAD,
    ATTR_UNIT,
    CONF_DEVICE_ID,
    CONF_PRESENCE_TOPIC,
    DEFAULT_PRESENCE_TOPIC,
    DOMAIN,
    MAX_DISPENSE_ML,
    MIN_DISPENSE_ML,
    SERVICE_DISPENSE,
    SERVICE_SEND_COMMAND,
)
from .protocol import SUPPORTED_UNITS, to_milliliters
from .runtime import Faucet

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type LocalDeltaConfigEntry = ConfigEntry[Faucet]

DISPENSE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_AMOUNT): vol.All(vol.Coerce(float), vol.Range(min=0, min_included=False)),
        vol.Optional(ATTR_UNIT, default="mL"): vol.In(SUPPORTED_UNITS),
    }
)
SEND_COMMAND_SCHEMA = vol.Schema(
    {vol.Required(ATTR_DEVICE_ID): cv.string, vol.Required(ATTR_PAYLOAD): cv.string}
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's actions once, for every faucet."""

    def faucet_for(call: ServiceCall) -> Faucet:
        device = dr.async_get(hass).async_get(call.data[ATTR_DEVICE_ID])
        if device is not None:
            for entry_id in device.config_entries:
                entry = hass.config_entries.async_get_entry(entry_id)
                if (
                    entry is not None
                    and entry.domain == DOMAIN
                    and entry.state is ConfigEntryState.LOADED
                ):
                    faucet: Faucet = entry.runtime_data
                    return faucet
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="unknown_device")

    async def dispense(call: ServiceCall) -> None:
        ml = to_milliliters(call.data[ATTR_AMOUNT], call.data[ATTR_UNIT])
        if not MIN_DISPENSE_ML <= ml <= MAX_DISPENSE_ML:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="dispense_out_of_range",
                translation_placeholders={
                    "ml": str(ml),
                    "min": str(MIN_DISPENSE_ML),
                    "max": str(MAX_DISPENSE_ML),
                },
            )
        await faucet_for(call).async_dispense(ml)

    async def send_command(call: ServiceCall) -> None:
        await faucet_for(call).async_send_command(call.data[ATTR_PAYLOAD])

    hass.services.async_register(DOMAIN, SERVICE_DISPENSE, dispense, DISPENSE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SEND_COMMAND, send_command, SEND_COMMAND_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: LocalDeltaConfigEntry) -> bool:
    """Subscribe to one faucet's topics."""
    if not await mqtt.async_wait_for_mqtt_client(hass):
        raise ConfigEntryNotReady("MQTT is not connected")
    device_id: str = entry.data[CONF_DEVICE_ID]
    presence = entry.options.get(
        CONF_PRESENCE_TOPIC, DEFAULT_PRESENCE_TOPIC.format(device_id=device_id)
    )
    faucet = Faucet(hass, device_id, presence)
    await faucet.async_start()
    entry.runtime_data = faucet
    entry.async_on_unload(faucet.async_stop)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LocalDeltaConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: LocalDeltaConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
