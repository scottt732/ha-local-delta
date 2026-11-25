# Local Delta Faucet

A Home Assistant integration for a **Delta VoiceIQ** faucet that talks to your own MQTT
broker instead of Delta's Azure cloud.

Delta's cloud stopped working for these faucets when Azure IoT Hub moved off the
Baltimore CyberTrust root, the only root the faucet's ZentriOS Wi-Fi module trusts. The
faucet itself still works. Give it a CA it trusts and a DNS name that points at your
broker, and this integration does the rest.

## What you get

| Entity | Notes |
| --- | --- |
| **Water** switch | Opens and closes the valve. The handle must be in the open position. The faucet never reports its valve, so the switch shows the last command sent. |
| **Dispense** button | Runs the amount set on *Dispense amount*. |
| **Dispense amount** | In fl. oz. on a US customary system, mL otherwise. |
| **Connected** | From the broker's client connect/disconnect events (see below). |
| **Faucet firmware**, **Firmware bundle**, **Last reset reason** | From the status report the faucet sends when it connects. |
| **Last usage** | Only fills in if your faucet reports usage. Ours has not; Delta's cloud computed usage itself. |

Actions:

- `local_delta.dispense`: amount plus a unit (mL, L, fl. oz., cups, gal). Capped at one gallon.
- `local_delta.send_command`: sends exact text to the faucet, for exploring its protocol.

## What the faucet actually does

- MQTT 3.1.1 over **TLS 1.0** only, cipher `ECDHE-RSA-AES256-SHA`. It sends SNI.
- It connects to `touch2Ovoice-IoTHub.azure-devices.net:8883` with client ID = its Wi-Fi
  MAC in upper-case hex, a username of
  `touch2Ovoice-IoTHub.azure-devices.net/<mac>/api-version=2016-11-14`, no password, and a
  self-signed client certificate.
- It subscribes to `devices/<mac>/messages/devicebound/#` and `$iothub/methods/POST/#`.
- It publishes to `devices/<mac>/messages/events/`. In testing it sent only a status
  report on connect, and nothing when someone used it.
- **Commands are matched as literal text.** `{"dispense": "100"}` runs 100 mL;
  `{"dispense":"100"}`, without the space, is delivered and silently ignored. This
  integration always sends the spaced form, so build raw commands the same way.
- Known commands, which mirror Delta's cloud API (`Dispense`, `changeState`):

  | Command | Effect |
  | --- | --- |
  | `{"dispense": "<mL>"}` | Runs that many mL, then closes. |
  | `{"state": "on"}` / `{"state": "off"}` | Opens or closes the valve. |

## Broker setup

The broker must:

1. Present a certificate for `touch2Ovoice-IoTHub.azure-devices.net`, signed by a CA you
   have installed on the faucet as `bc2025.crt`.
2. Accept TLS 1.0 with `ECDHE-RSA-AES256-SHA` on the faucet's listener.
3. Let the faucet connect without a password. Scope it with an ACL by client ID:
   publish to `devices/<mac>/messages/events/#` and `$iothub/methods/res/#`, subscribe
   to its devicebound and methods topics.
4. Let Home Assistant's MQTT user publish to the faucet's devicebound topic and
   subscribe to its events.

For the **Connected** sensor, Home Assistant's MQTT user also needs to subscribe to
`$SYS/brokers/+/clients/<mac>/+`. `#` does not match topics that start with `$`. The
default topic fits EMQX. Change it under the integration's options, or clear it if your
broker has no such events.

Never read or write files on the faucet's Wi-Fi module over its HTTP API: binary reads
crash it. Push files with its `http_download` command instead.

## Install

Add this repository to HACS as a custom integration repository, install **Local Delta
Faucet**, restart, then add the integration and enter the faucet's Wi-Fi MAC.

## Credit

The dispense command and the CA swap come from u/Velaar's write-up on r/homeassistant.
