"""The per-faucet runtime: MQTT subscriptions, state and command publishing."""

from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.components import mqtt
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback

from .protocol import (
    FaucetState,
    command_topic,
    dispense_payload,
    events_topic,
    state_payload,
)

_LOGGER = logging.getLogger(__name__)


class Faucet:
    """One faucet on the broker."""

    def __init__(self, hass: HomeAssistant, device_id: str, presence_topic: str) -> None:
        self.hass = hass
        self.device_id = device_id
        self.presence_topic = presence_topic
        self.state = FaucetState()
        # Set by the Dispense amount entity; the Dispense button sends it.
        self.dispense_ml = 250
        self._listeners: list[Callable[[], None]] = []
        self._unsubscribe: list[CALLBACK_TYPE] = []

    async def async_start(self) -> None:
        self._unsubscribe.append(
            await mqtt.async_subscribe(self.hass, events_topic(self.device_id), self._on_event)
        )
        if self.presence_topic:
            self._unsubscribe.append(
                await mqtt.async_subscribe(self.hass, self.presence_topic, self._on_presence)
            )

    @callback
    def async_stop(self) -> None:
        while self._unsubscribe:
            self._unsubscribe.pop()()

    @callback
    def async_add_listener(self, update: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.append(update)

        @callback
        def remove() -> None:
            self._listeners.remove(update)

        return remove

    @callback
    def _notify(self) -> None:
        for update in list(self._listeners):
            update()

    @callback
    def _on_event(self, msg: mqtt.ReceiveMessage) -> None:
        if self.state.apply_event(msg.payload):
            self._notify()
        else:
            _LOGGER.debug("Ignoring non-JSON message on %s: %r", msg.topic, msg.payload)

    @callback
    def _on_presence(self, msg: mqtt.ReceiveMessage) -> None:
        event = msg.topic.rsplit("/", 1)[-1]
        if event == "connected":
            self.state.connected = True
        elif event == "disconnected":
            self.state.connected = False
        else:
            return
        self._notify()

    async def async_dispense(self, milliliters: int) -> None:
        await self.async_send_command(dispense_payload(milliliters))

    async def async_set_water(self, on: bool) -> None:
        await self.async_send_command(state_payload(on))
        # The faucet does not report its valve, so remember what we asked for.
        self.state.water_on = on
        self._notify()

    async def async_send_command(self, payload: str) -> None:
        _LOGGER.debug("Sending %s to faucet %s", payload, self.device_id)
        await mqtt.async_publish(self.hass, command_topic(self.device_id), payload, qos=0)
