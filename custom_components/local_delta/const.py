"""Constants for the Local Delta Faucet integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "local_delta"

CONF_DEVICE_ID: Final = "device_id"
CONF_PRESENCE_TOPIC: Final = "presence_topic"

# EMQX publishes these when a client connects or disconnects. The Home Assistant MQTT
# user needs an ACL grant for them: "#" does not match topics that start with "$".
DEFAULT_PRESENCE_TOPIC: Final = "$SYS/brokers/+/clients/{device_id}/+"

# The faucet has no documented limit; one US gallon keeps a typo from flooding the sink.
MIN_DISPENSE_ML: Final = 1
MAX_DISPENSE_ML: Final = 3785

SERVICE_DISPENSE: Final = "dispense"
SERVICE_SEND_COMMAND: Final = "send_command"
ATTR_AMOUNT: Final = "amount"
ATTR_UNIT: Final = "unit"
ATTR_PAYLOAD: Final = "payload"
ATTR_DEVICE_ID: Final = "device_id"
