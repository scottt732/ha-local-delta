"""Dispense button: sends the amount set on the Dispense amount entity."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
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
            DispenseButton(
                entry.runtime_data,
                ButtonEntityDescription(key="dispense", translation_key="dispense"),
            )
        ]
    )


class DispenseButton(LocalDeltaEntity, ButtonEntity):
    async def async_press(self) -> None:
        await self.faucet.async_dispense(self.faucet.dispense_ml)
