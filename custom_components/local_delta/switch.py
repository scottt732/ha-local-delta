"""Water switch: opens and closes the valve when the handle is in the open position."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LocalDeltaConfigEntry
from .entity import LocalDeltaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LocalDeltaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        [
            WaterSwitch(
                entry.runtime_data, SwitchEntityDescription(key="water", translation_key="water")
            )
        ]
    )


class WaterSwitch(LocalDeltaEntity, SwitchEntity):
    # The faucet never reports its valve: someone can close it at the handle or by touch,
    # and a dispense closes it when done. Show the last command and keep both buttons live.
    _attr_assumed_state = True

    @property
    def is_on(self) -> bool | None:
        return self.faucet.state.water_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.faucet.async_set_water(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.faucet.async_set_water(False)
