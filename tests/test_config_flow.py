"""Config flow."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.local_delta.const import DOMAIN


async def test_user_flow_normalizes_the_mac(hass: HomeAssistant, mqtt_mock):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Kitchen faucet", "device_id": "60:a4:23:00:00:01"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"device_id": "60A423000001"}


async def test_user_flow_rejects_bad_mac(hass: HomeAssistant, mqtt_mock):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Kitchen faucet", "device_id": "nope"}
    )
    assert result["errors"] == {"device_id": "invalid_device_id"}
