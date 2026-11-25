"""Sensors: firmware and reset diagnostics, and water use if the faucet reports it."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LocalDeltaConfigEntry
from .entity import LocalDeltaEntity
from .protocol import FaucetState


@dataclass(frozen=True, kw_only=True)
class LocalDeltaSensorDescription(SensorEntityDescription):
    value: Callable[[FaucetState], str | float | None]


SENSORS = (
    # The faucet has only been seen to send "usage" on Velaar's firmware; ours has not
    # sent one yet. Volume, not water: HA's water class demands a running total, and
    # nothing says this is one. Home Assistant converts mL to the user's units.
    LocalDeltaSensorDescription(
        key="last_usage",
        translation_key="last_usage",
        device_class=SensorDeviceClass.VOLUME,
        native_unit_of_measurement=UnitOfVolume.MILLILITERS,
        suggested_display_precision=0,
        value=lambda s: s.usage_ml,
    ),
    LocalDeltaSensorDescription(
        key="mcu_firmware",
        translation_key="mcu_firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda s: s.mcu_firmware,
    ),
    LocalDeltaSensorDescription(
        key="bundle_version",
        translation_key="bundle_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda s: s.bundle_version,
    ),
    LocalDeltaSensorDescription(
        key="wifi_os",
        translation_key="wifi_os",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value=lambda s: s.os_version,
    ),
    LocalDeltaSensorDescription(
        key="reset_reason",
        translation_key="reset_reason",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda s: s.reset_reason,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LocalDeltaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(LocalDeltaSensor(entry.runtime_data, d) for d in SENSORS)


class LocalDeltaSensor(LocalDeltaEntity, SensorEntity):
    entity_description: LocalDeltaSensorDescription

    @property
    def native_value(self) -> str | float | None:
        return self.entity_description.value(self.faucet.state)
