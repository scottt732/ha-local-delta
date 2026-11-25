"""Dispense amount, in the user's own units, which the Dispense button sends."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntityDescription,
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.unit_conversion import VolumeConverter
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from . import LocalDeltaConfigEntry
from .const import MAX_DISPENSE_ML, MIN_DISPENSE_ML
from .entity import LocalDeltaEntity
from .protocol import to_milliliters
from .runtime import Faucet

# (unit, default, step) per unit system. NumberEntity only converts temperatures, so the
# entity picks the unit itself and converts on the way out.
US = (UnitOfVolume.FLUID_OUNCES, 8.0, 0.5)
METRIC = (UnitOfVolume.MILLILITERS, 250.0, 10.0)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LocalDeltaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    unit, default, step = US if hass.config.units is US_CUSTOMARY_SYSTEM else METRIC
    async_add_entities([DispenseAmount(entry.runtime_data, unit, default, step)])


class DispenseAmount(LocalDeltaEntity, RestoreNumber):
    _attr_mode = NumberMode.BOX

    def __init__(self, faucet: Faucet, unit: str, default: float, step: float) -> None:
        super().__init__(
            faucet,
            NumberEntityDescription(
                key="dispense_amount",
                translation_key="dispense_amount",
                device_class=NumberDeviceClass.VOLUME,
            ),
        )
        self._attr_native_unit_of_measurement = unit
        self._attr_native_step = step
        self._attr_native_min_value = step
        self._attr_native_max_value = _from_ml(MAX_DISPENSE_ML, unit)
        self._default = default
        self._attr_native_value = default

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if (
            last is not None
            and last.native_value is not None
            and last.native_unit_of_measurement == self.native_unit_of_measurement
        ):
            self._attr_native_value = last.native_value
        self._publish()

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self._publish()
        self.async_write_ha_state()

    def _publish(self) -> None:
        unit = self.native_unit_of_measurement or UnitOfVolume.MILLILITERS
        ml = to_milliliters(self._attr_native_value or self._default, unit)
        self.faucet.dispense_ml = max(MIN_DISPENSE_ML, min(MAX_DISPENSE_ML, ml))


def _from_ml(ml: int, unit: str) -> float:
    return round(VolumeConverter.convert(ml, UnitOfVolume.MILLILITERS, unit), 1)
