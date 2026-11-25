"""The wire protocol, without Home Assistant running."""

from __future__ import annotations

import json

import pytest

from custom_components.local_delta.protocol import (
    FaucetState,
    command_topic,
    dispense_payload,
    normalize_device_id,
    to_milliliters,
)

STATUS = (
    '{ "status": "ok","mcuBoot": {"BootMajor": 0,"BootMinor": 0,"BootRevision": 3},'
    '"mcuVer": {"FirmMajor": 2,"FirmMinor": 1,"FirmRevision": 7},"side": "a",'
    '"OSName": "ZentriOS-WL","productID": "DELTA1-VOICE","boardVersion": "1","valveRev": "2",'
    '"OSVersion": {"Major": 1,"Minor": 5,"Revision": 0,"build": 13},'
    '"BundleV": {"Major": 2,"Minor": 1,"Revision": 2,"build": 0},'
    '"Outage": {"Duration": 0,"Reason": "Reset","StateChanges": 0}, "brand": 1 }'
)


def test_dispense_payload_keeps_the_space_the_faucet_requires():
    assert dispense_payload(100) == '{"dispense": "100"}'
    assert json.loads(dispense_payload(100)) == {"dispense": "100"}


def test_command_topic_carries_the_iot_hub_property_bag():
    assert command_topic("60A423000001") == (
        "devices/60A423000001/messages/devicebound/"
        "%24.to=%2Fdevices%2F60A423000001%2Fmessages%2FdeviceBound"
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [("60:a4:23:00:00:01", "60A423000001"), ("60-A4-23-00-00-01", "60A423000001")],
)
def test_normalize_device_id(value, expected):
    assert normalize_device_id(value) == expected


def test_normalize_device_id_rejects_short_values():
    with pytest.raises(ValueError):
        normalize_device_id("60:a4:23")


@pytest.mark.parametrize(
    ("amount", "unit", "ml"),
    [(250, "mL", 250), (1, "L", 1000), (8, "fl. oz.", 237), (1, "cups", 237), (1, "gal", 3785)],
)
def test_to_milliliters(amount, unit, ml):
    assert to_milliliters(amount, unit) == ml


def test_to_milliliters_rejects_unknown_units():
    with pytest.raises(ValueError):
        to_milliliters(1, "pints")


def test_status_report_fills_diagnostics():
    state = FaucetState()
    assert state.apply_event(STATUS)
    assert state.connected is True
    assert state.mcu_firmware == "2.1.7"
    assert state.bundle_version == "2.1.2.0"
    assert state.os_version == "ZentriOS-WL 1.5.0.13"
    assert state.reset_reason == "Reset"
    assert state.usage_ml is None


def test_usage_and_state_messages():
    state = FaucetState()
    state.apply_event('{"usage": "350", "state": "off"}')
    assert state.usage_ml == 350
    assert state.water_on is False


def test_non_json_is_ignored():
    state = FaucetState()
    assert not state.apply_event(b"\x00garbage")
    assert state.connected is None
