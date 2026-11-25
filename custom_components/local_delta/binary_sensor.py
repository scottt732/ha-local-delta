"""Binary sensors: broker connection, and water running if the faucet reports it."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LocalDeltaConfigEntry
from .entity import LocalDeltaEntity
from .protocol import FaucetState


@dataclass(frozen=True, kw_only=True)
class LocalDeltaBinarySensorDescription(BinarySensorEntityDescription):
    value: Callable[[FaucetState], bool | None]


BINARY_SENSORS = (
    LocalDeltaBinarySensorDescription(
        key="connected",
        translation_key="connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda s: s.connected,
    ),
    LocalDeltaBinarySensorDescription(
        key="water_running",
        translation_key="water_running",
        device_class=BinarySensorDeviceClass.RUNNING,
        value=lambda s: s.water_on,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LocalDeltaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(LocalDeltaBinarySensor(entry.runtime_data, d) for d in BINARY_SENSORS)


class LocalDeltaBinarySensor(LocalDeltaEntity, BinarySensorEntity):
    entity_description: LocalDeltaBinarySensorDescription

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value(self.faucet.state)
