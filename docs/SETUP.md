# Setting up a faucet for local control

This integration only talks MQTT. The faucet was never meant to talk to anything
but Delta's Azure IoT Hub, so getting it onto your own broker takes some work
outside Home Assistant. Budget an hour. You need:

- **A router whose DNS you can override** for one hostname. UniFi, pfSense,
  OPNsense, Pi-hole, AdGuard Home and plain dnsmasq all can.
- **An MQTT broker that still accepts TLS 1.0.** The faucet's 2019 Wi-Fi
  module speaks nothing newer. EMQX and Mosquitto both work. The broker must be
  the one Home Assistant's MQTT integration uses.
- **A computer with Python 3.9 or newer and `openssl`**, and Wi-Fi so it can
  join the faucet's setup network.
- **Plain HTTP from the faucet to that computer** for one minute, so the faucet
  can download a file from it. On a flat home network this just works. Firewalled
  VLANs may need a temporary rule; see [Uploading the CA](#uploading-the-ca).

`scripts/faucet_setup.py` does every step that touches the faucet and tells you
when to switch networks. The rest of this page explains what it does and covers
the router and broker parts, which differ for everyone.

```sh
python3 scripts/faucet_setup.py          # guided, start to finish
python3 scripts/faucet_setup.py --help   # or one step at a time
```

## How it works

The faucet's VoiceIQ module is a Zentri (now Silicon Labs) Wi-Fi module running
ZentriOS. The faucet's own controller tells it to open MQTT over TLS to
`touch2Ovoice-IoTHub.azure-devices.net:8883`, trusting exactly one certificate
authority, stored on the module as `bc2025.crt`. That was the Baltimore
CyberTrust Root. Azure stopped using it, which is why so many of these faucets
went offline.

So we change two things, and leave the faucet's controller alone:

1. **The trusted CA.** Replace the contents of `bc2025.crt` with a CA you make.
   The controller sets the file name at every boot, so the name stays.
2. **Where the hub name points.** Your router's DNS answers
   `touch2Ovoice-IoTHub.azure-devices.net` with your broker's address. Your
   broker presents a certificate for that name, signed by your CA.

The faucet then connects to your broker, thinking it is Azure.

The [ZentriOS reference](https://web.archive.org/web/20240301034423/https://docs.zentri.com/zentrios/w/latest/) (archived) documents
every module command used here. The faucet's MQTT commands were first found by
Velaar in the
[r/homeassistant thread](https://www.reddit.com/r/homeassistant/comments/101lp3w/controlling_delta_voice_iq_faucet_from_ha/);
see the README's credits for everyone else.

## 1. Make certificates

```sh
python3 scripts/faucet_setup.py certs
```

This writes `faucet-pki/`: a private CA (`ca.pem`, `ca.der`, `ca.key`) and a
server certificate for the hub name (`server.pem`, `server.key`). They expire on
2037-12-31, before the module's 32-bit clock runs out. Keep `ca.key` offline.
You need it only to re-sign the server certificate.

## 2. Put the faucet in setup mode and join your Wi-Fi

A faucet with no saved Wi-Fi starts in setup mode on its own. The module under
the sink blinks green, and it broadcasts a Wi-Fi network named
`ZentriOS Web Setup XXX`, where `XXX` is the end of its MAC address. Its
password is usually `password`. The module's address on that network is always
`10.10.10.1`.

```sh
python3 scripts/faucet_setup.py join
```

The script waits for `10.10.10.1` to answer, saves a read-only backup, asks for
your Wi-Fi name and password, and sets:

| Setting | Why |
| ------- | --- |
| `wlan.ssid`, `wlan.passkey`, `wlan.auto_join.enabled 1` | join your network |
| `wlan.dhcp.hostname` | find it in your router's client list |
| `http.server.enabled 1`, `api_enabled 1`, `interface wlan` | keep the HTTP command API reachable on your LAN, for the next step and for troubleshooting |

Then it restarts the module. Rejoin your normal network and find the faucet's
IP address in your router. Give it a DHCP reservation.

The faucet needs **2.4 GHz** Wi-Fi. An IoT network or VLAN is a good home for it.

## 3. Uploading the CA

```sh
python3 scripts/faucet_setup.py upload --host <faucet IP>
```

The module can't receive uploads; it can only download (`hdo`, HTTP download).
So the script serves `ca.der` from your computer on port 8765 and tells the
faucet to fetch it. It downloads to a test name first and checks the size, and
only then replaces `bc2025.crt`.

Until the faucet trusts your broker, its controller restarts the Wi-Fi module
about every 42 seconds. The script waits for a restart before it starts, so
nothing is cut off halfway.

**If the download fails**, the faucet can't reach your computer. Common causes:
your computer's firewall blocks port 8765 (allow it for a minute), or the faucet's
VLAN can't reach yours. Fix it with a temporary firewall rule. Or serve `ca.der`
from any plain-HTTP host the faucet can reach, and pass that host with
`--serve-ip` and `--port`.

**Do not** use the module's file-reading or file-writing commands (`fop`/`read`,
`fcr`/`write`) over its HTTP API. Reading binary files crashes the module.

## 4. Point DNS at your broker

Add one DNS record on your router, answering
`touch2Ovoice-IoTHub.azure-devices.net` with your broker's IP address. Examples:

| Router | Where |
| ------ | ----- |
| UniFi | Settings → Policy Engine → DNS → Create Entry (Host (A)) |
| pfSense, OPNsense | Services → DNS Resolver (Unbound) → Host Overrides |
| Pi-hole | Local DNS → DNS Records |
| AdGuard Home | Filters → DNS rewrites |
| dnsmasq | `address=/touch2Ovoice-IoTHub.azure-devices.net/192.0.2.10` |

The faucet must use that DNS server. It does if it gets its DNS from DHCP, which
is the default.

This record also sends any other device asking for that name to your broker.
Only Delta faucets use it.

## 5. Give your broker a TLS listener for the faucet

The faucet connects to **port 8883** with:

- TLS 1.0, cipher `ECDHE-RSA-AES256-SHA`
- SNI `touch2Ovoice-IoTHub.azure-devices.net`
- MQTT 3.1.1, client ID = its MAC address in capitals without colons
  (`60A423XXXXXX`)
- an Azure-style username and **no password**
- a self-signed client certificate, which you can ignore

So the listener must allow TLS 1.0, use `server.pem` and `server.key`, and accept
the faucet without a password. Restrict it by client ID with an ACL instead:

- publish `devices/<id>/messages/events/#` and `$iothub/methods/res/#`
- subscribe `devices/<id>/messages/devicebound/#` and `$iothub/methods/POST/#`

Home Assistant needs to publish to `devices/<id>/messages/devicebound/#` and to
read `devices/<id>/messages/events/#`.

### EMQX 5

Add a separate SSL listener, so your other listeners keep their settings.
As environment variables:

```sh
EMQX_LISTENERS__SSL__FAUCET__BIND="0.0.0.0:8883"
EMQX_LISTENERS__SSL__FAUCET__ENABLE_AUTHN="false"
EMQX_LISTENERS__SSL__FAUCET__SSL_OPTIONS__CERTFILE=/path/server.pem
EMQX_LISTENERS__SSL__FAUCET__SSL_OPTIONS__KEYFILE=/path/server.key
EMQX_LISTENERS__SSL__FAUCET__SSL_OPTIONS__VERIFY=verify_none
EMQX_LISTENERS__SSL__FAUCET__SSL_OPTIONS__VERSIONS='["tlsv1.2","tlsv1.1","tlsv1"]'
EMQX_LISTENERS__SSL__FAUCET__SSL_OPTIONS__CIPHERS='["ECDHE-RSA-AES256-GCM-SHA384","ECDHE-RSA-AES256-SHA"]'
```

If 8883 is taken, bind the faucet listener to another port and forward 8883 on a
second IP address to it. Presence works out of the box: set the integration's
presence topic to `$SYS/brokers/+/clients/{device_id}/+`, and let Home
Assistant's MQTT user subscribe to it.

### Mosquitto 2

A separate listener, so `allow_anonymous` applies only to it:

```conf
per_listener_settings true

listener 8883
certfile /mosquitto/certs/server.pem
keyfile /mosquitto/certs/server.key
require_certificate false
allow_anonymous true
acl_file /mosquitto/config/faucet.acl
```

If your Mosquitto build's OpenSSL refuses TLS 1.0, add
`ciphers ECDHE-RSA-AES256-SHA:@SECLEVEL=0`. Mosquitto has no presence topic per
client, so leave the integration's presence topic empty. The Connected sensor
then stays unknown.

## 6. Check it

```sh
python3 scripts/faucet_setup.py verify --host <faucet IP>
```

This watches the module's uptime. While it can't connect, uptime resets about
every 42 seconds. Once it climbs past two minutes, the faucet is on your broker.
Your broker's client list shows `60A423XXXXXX`.

Then add the integration in Home Assistant with the faucet's MAC address.

## Undoing it

Save the Baltimore CyberTrust Root from DigiCert as `ca.der` in a folder of its
own, run `upload --host <faucet IP> --pki <that folder>`, and remove the DNS
record. The faucet goes back to
trying Azure, which no longer accepts it.
