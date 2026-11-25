"""Setup, entities and actions against a mocked MQTT broker."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_mqtt_message,
)

from custom_components.local_delta.const import DOMAIN

from .test_protocol import STATUS

DID = "60A423000001"
TOPIC = f"devices/{DID}/messages/devicebound/%24.to=%2Fdevices%2F{DID}%2Fmessages%2FdeviceBound"


@pytest.fixture
async def entry(hass: HomeAssistant, mqtt_mock):
    entry = MockConfigEntry(
        domain=DOMAIN, title="Kitchen faucet", unique_id=DID, data={"device_id": DID}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def device_id(hass: HomeAssistant) -> str:
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, DID)})
    assert device is not None
    return device.id


async def test_status_report_updates_sensors(hass: HomeAssistant, entry):
    async_fire_mqtt_message(hass, f"devices/{DID}/messages/events/", STATUS)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.kitchen_faucet_faucet_firmware").state == "2.1.7"
    assert hass.states.get("sensor.kitchen_faucet_last_reset_reason").state == "Reset"
    assert hass.states.get("binary_sensor.kitchen_faucet_connected").state == "on"


async def test_broker_presence(hass: HomeAssistant, entry):
    async_fire_mqtt_message(hass, f"$SYS/brokers/emqx@n1/clients/{DID}/disconnected", "{}")
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.kitchen_faucet_connected").state == "off"


async def test_dispense_action_converts_units(hass: HomeAssistant, entry, mqtt_mock):
    await hass.services.async_call(
        DOMAIN,
        "dispense",
        {"device_id": device_id(hass), "amount": 8, "unit": "fl. oz."},
        blocking=True,
    )
    assert mqtt_mock.async_publish.call_args.args[:3] == (TOPIC, '{"dispense": "237"}', 0)


async def test_dispense_action_rejects_a_flood(hass: HomeAssistant, entry):
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "dispense",
            {"device_id": device_id(hass), "amount": 2, "unit": "gal"},
            blocking=True,
        )


async def test_button_sends_the_number_amount(hass: HomeAssistant, entry, mqtt_mock):
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.kitchen_faucet_dispense_amount", "value": 500},
        blocking=True,
    )
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.kitchen_faucet_dispense"}, blocking=True
    )
    assert mqtt_mock.async_publish.call_args.args[:3] == (TOPIC, '{"dispense": "500"}', 0)


async def test_unload(hass: HomeAssistant, entry):
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_water_switch(hass: HomeAssistant, entry, mqtt_mock):
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.kitchen_faucet_water"}, blocking=True
    )
    assert mqtt_mock.async_publish.call_args.args[:3] == (TOPIC, '{"state": "on"}', 0)
    assert hass.states.get("switch.kitchen_faucet_water").state == "on"
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.kitchen_faucet_water"}, blocking=True
    )
    assert mqtt_mock.async_publish.call_args.args[:3] == (TOPIC, '{"state": "off"}', 0)
    assert hass.states.get("switch.kitchen_faucet_water").state == "off"
