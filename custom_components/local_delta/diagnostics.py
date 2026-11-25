"""Diagnostics: the faucet's last status report and last message."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import LocalDeltaConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: LocalDeltaConfigEntry
) -> dict[str, Any]:
    faucet = entry.runtime_data
    return {
        "presence_topic": faucet.presence_topic,
        "connected": faucet.state.connected,
        "status": faucet.state.status,
        "last_message": faucet.state.last_message,
        "dispense_ml": faucet.dispense_ml,
    }
