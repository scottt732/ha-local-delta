"""The faucet's wire protocol, kept free of Home Assistant so it is easy to test.

The faucet speaks Azure IoT Hub's MQTT dialect to whatever broker its DNS points at.
Its device ID is its Wi-Fi MAC in upper-case hex, such as ``60A423000001``.
"""

from __future__ import annotations

import contextlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Final

from homeassistant.const import UnitOfVolume
from homeassistant.util.unit_conversion import VolumeConverter

DEVICE_ID_RE: Final = re.compile(r"^[0-9A-F]{12}$")

UNIT_CUPS: Final = "cups"
ML_PER_CUP: Final = 236.5882365

SUPPORTED_UNITS: Final = (
    UnitOfVolume.MILLILITERS,
    UnitOfVolume.LITERS,
    UnitOfVolume.FLUID_OUNCES,
    UNIT_CUPS,
    UnitOfVolume.GALLONS,
)


def normalize_device_id(value: str) -> str:
    """Accept a MAC in any common spelling and return the faucet's device ID."""
    device_id = re.sub(r"[^0-9A-Fa-f]", "", value).upper()
    if not DEVICE_ID_RE.match(device_id):
        raise ValueError(f"not a 12-digit MAC address: {value!r}")
    return device_id


def events_topic(device_id: str) -> str:
    """Topic the faucet publishes telemetry on."""
    return f"devices/{device_id}/messages/events/#"


def command_topic(device_id: str) -> str:
    """Topic the faucet takes cloud-to-device commands on, with IoT Hub's property bag."""
    return (
        f"devices/{device_id}/messages/devicebound/"
        f"%24.to=%2Fdevices%2F{device_id}%2Fmessages%2FdeviceBound"
    )


def to_milliliters(amount: float, unit: str) -> int:
    """Convert an amount to whole milliliters."""
    if unit == UNIT_CUPS:
        ml = amount * ML_PER_CUP
    elif unit in SUPPORTED_UNITS:
        ml = VolumeConverter.convert(amount, unit, UnitOfVolume.MILLILITERS)
    else:
        raise ValueError(f"unsupported unit: {unit!r}")
    return round(ml)


def dispense_payload(milliliters: int) -> str:
    """Build the dispense command.

    The faucet matches this text literally. The space after the colon is required:
    compact JSON such as ``{"dispense":"100"}`` is delivered and silently ignored, so
    never build this with ``json.dumps(..., separators=...)`` or a Jinja ``tojson``.
    """
    return f'{{"dispense": "{int(milliliters)}"}}'


@dataclass
class FaucetState:
    """Everything the faucet has told us since Home Assistant started."""

    connected: bool | None = None
    status: dict[str, Any] = field(default_factory=dict)
    usage_ml: float | None = None
    water_on: bool | None = None
    last_message: dict[str, Any] = field(default_factory=dict)

    def apply_event(self, payload: str | bytes | bytearray) -> bool:
        """Fold one telemetry message in. Returns False if it was not JSON."""
        try:
            data = json.loads(payload)
        except TypeError, ValueError:
            return False
        if not isinstance(data, dict):
            return False
        self.last_message = data
        # The faucet only talks while connected, whatever presence said last.
        self.connected = True
        if "status" in data:
            self.status = data
        if "usage" in data:
            with contextlib.suppress(TypeError, ValueError):
                self.usage_ml = float(data["usage"])
        if "state" in data:
            self.water_on = _truthy(data["state"])
        return True

    @property
    def mcu_firmware(self) -> str | None:
        return _version(self.status.get("mcuVer"), "Firm")

    @property
    def bundle_version(self) -> str | None:
        return _version(self.status.get("BundleV"), "")

    @property
    def os_version(self) -> str | None:
        name = self.status.get("OSName")
        ver = _version(self.status.get("OSVersion"), "")
        return " ".join(p for p in (name, ver) if p) or None

    @property
    def reset_reason(self) -> str | None:
        outage = self.status.get("Outage")
        return outage.get("Reason") if isinstance(outage, dict) else None


def _version(value: Any, prefix: str) -> str | None:
    if not isinstance(value, dict):
        return None
    parts = [value.get(f"{prefix}{k}") for k in ("Major", "Minor", "Revision")]
    if any(p is None for p in parts):
        return None
    build = value.get("build")
    text = ".".join(str(p) for p in parts)
    return f"{text}.{build}" if build is not None else text


def _truthy(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("on", "true", "1", "open", "running"):
            return True
        if v in ("off", "false", "0", "closed", "idle"):
            return False
    return None
