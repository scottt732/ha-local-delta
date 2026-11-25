"""Base entity: one device per faucet, refreshed whenever the faucet says anything."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription

from .const import DOMAIN
from .runtime import Faucet


class LocalDeltaEntity(Entity):
    """Shared device info and push updates."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, faucet: Faucet, description: EntityDescription) -> None:
        self.faucet = faucet
        self.entity_description = description
        did = faucet.device_id
        self._attr_unique_id = f"{did}_{description.key}"
        mac = ":".join(did[i : i + 2] for i in range(0, 12, 2)).lower()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, did)},
            connections={(CONNECTION_NETWORK_MAC, mac)},
            manufacturer="Delta Faucet",
            model="VoiceIQ",
            sw_version=faucet.state.mcu_firmware,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.faucet.async_add_listener(self.async_write_ha_state))
