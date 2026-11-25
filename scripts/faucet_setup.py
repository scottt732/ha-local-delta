#!/usr/bin/env python3
"""Guided setup for running a Delta VoiceIQ faucet on your own MQTT broker.

Walks through the steps in docs/SETUP.md, telling you when to switch Wi-Fi
networks and waiting for the faucet to answer before each step. It needs only
Python 3.9+ and the `openssl` command, and runs the same on macOS, Linux and
Windows.

    python3 scripts/faucet_setup.py            # the whole guided flow
    python3 scripts/faucet_setup.py --help     # or run one step at a time

Steps, in order:
    certs     make a private CA and a server certificate for your broker
    backup    save the faucet's settings (read only)
    join      join your Wi-Fi and turn on the faucet's HTTP API (setup mode)
    upload    replace the faucet's trusted CA with yours (on your LAN)
    verify    watch the faucet stay connected

What this script never does: read files off the faucet (binary reads crash
the module) or change anything on your router or broker.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import functools
import getpass
import http.server
import json
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

SETUP_IP = "10.10.10.1"
DEFAULT_HUB = "touch2Ovoice-IoTHub.azure-devices.net"
# The faucet's TLS stack stores dates in 32 bits; stay clear of 2038.
NOT_AFTER = dt.date(2037, 12, 31)


# --------------------------------------------------------------------------
# Talking to the module
# --------------------------------------------------------------------------


class FaucetError(RuntimeError):
    pass


def command(host: str, cmd: str, timeout: float = 20) -> str:
    """Run one ZentriOS command over HTTP and return its response text."""
    url = f"http://{host}/command/{urllib.parse.quote(cmd, safe='')}"
    with urllib.request.urlopen(url, timeout=timeout) as reply:
        body = json.loads(reply.read().decode("utf-8", "replace"))
    if body.get("code") != 0:
        raise FaucetError(f"{cmd.split()[0]}: {body.get('response', '').strip()}")
    return str(body.get("response", "")).replace("\r", "").strip()


def answers(host: str) -> bool:
    try:
        command(host, "ver", timeout=3)
        return True
    except (OSError, ValueError, FaucetError):
        return False


def wait_for(host: str, what: str, limit: float = 900) -> None:
    """Poll until the module answers, printing a dot every few seconds."""
    print(f"Waiting for the faucet at {host} ({what}) ", end="", flush=True)
    deadline = time.monotonic() + limit
    while not answers(host):
        if time.monotonic() > deadline:
            print()
            sys.exit(
                f"Gave up after {int(limit / 60)} minutes. Check the steps above and run this step again."
            )
        print(".", end="", flush=True)
        time.sleep(3)
    print(" found it.")


def uptime(host: str) -> int | None:
    try:
        return int(command(host, "get time.uptime", timeout=5).split()[0])
    except (OSError, ValueError, FaucetError, IndexError):
        return None


def wait_for_fresh_boot(host: str) -> None:
    """Until the faucet trusts your broker, its controller restarts the Wi-Fi
    module about every 42 seconds. Start work right after a restart so a
    command is not cut off halfway."""
    print(
        "Waiting for the module's next restart, so the next steps get a full window ",
        end="",
        flush=True,
    )
    last = uptime(host) or 0
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        now = uptime(host)
        if now is not None and now < last:
            break
        last = now if now is not None else last
        print(".", end="", flush=True)
        time.sleep(2)
    wait_for(host, "back up after restart", limit=120)


def pause(text: str) -> None:
    print()
    print(text)
    input("Press Enter when ready... ")


# --------------------------------------------------------------------------
# Steps
# --------------------------------------------------------------------------


def step_certs(args: argparse.Namespace) -> None:
    """Make a private CA (for the faucet) and a server certificate (for the broker)."""
    if not shutil.which("openssl"):
        sys.exit("This step needs the openssl command. Install OpenSSL and try again.")
    out = Path(args.pki)
    out.mkdir(parents=True, exist_ok=True)
    if (out / "ca.key").exists():
        print(f"{out}/ca.key already exists; keeping the existing CA.")
    days = (NOT_AFTER - dt.date.today()).days
    hub = args.hub

    def run(*cmd: str) -> None:
        subprocess.run(cmd, cwd=out, check=True, capture_output=True)

    if not (out / "ca.key").exists():
        run("openssl", "genrsa", "-out", "ca.key", "2048")
        run(
            "openssl",
            "req",
            "-x509",
            "-new",
            "-key",
            "ca.key",
            "-sha256",
            "-days",
            str(days),
            "-subj",
            "/CN=Local Delta Faucet CA",
            "-addext",
            "basicConstraints=critical,CA:TRUE",
            "-addext",
            "keyUsage=critical,keyCertSign,cRLSign",
            "-out",
            "ca.pem",
        )
    # The faucet stores its CA in DER form.
    run("openssl", "x509", "-in", "ca.pem", "-outform", "DER", "-out", "ca.der")
    (out / "server.ext").write_text(
        f"subjectAltName=DNS:{hub},DNS:{hub.lower()}\n"
        "extendedKeyUsage=serverAuth\nkeyUsage=critical,digitalSignature,keyEncipherment\n"
    )
    run("openssl", "genrsa", "-out", "server.key", "2048")
    run("openssl", "req", "-new", "-key", "server.key", "-subj", f"/CN={hub}", "-out", "server.csr")
    run(
        "openssl",
        "x509",
        "-req",
        "-in",
        "server.csr",
        "-CA",
        "ca.pem",
        "-CAkey",
        "ca.key",
        "-CAcreateserial",
        "-sha256",
        "-days",
        str(days),
        "-extfile",
        "server.ext",
        "-out",
        "server.pem",
    )
    for key in ("ca.key", "server.key"):
        (out / key).chmod(0o600)
    print(f"""
Wrote {out}/:
  ca.der       goes on the faucet (the upload step does this)
  server.pem   your broker's certificate, for the faucet's TLS listener
  server.key   your broker's private key, for the same listener
  ca.key       keep this safe and offline; you need it only to re-sign server.pem
The certificates expire on {NOT_AFTER}.""")


def step_backup(args: argparse.Namespace) -> None:
    """Save the module's settings and file list. Reads only; writes nothing."""
    host = args.host or SETUP_IP
    wait_for(host, "to back up")
    out = Path(args.backup or f"faucet-backup-{dt.datetime.now():%Y%m%d-%H%M%S}")
    out.mkdir(parents=True, exist_ok=True)
    for name, cmd in (("ver", "ver"), ("files", "ls -v")):
        (out / f"{name}.txt").write_text(command(host, cmd) + "\n")
        print(f"  saved {name}.txt")
    try:
        settings = command(host, "get all")
    except (OSError, FaucetError):
        # Once on Wi-Fi the module lacks memory for "get all" (HTTP 500, "No Mem").
        groups = ("wlan", "network", "http", "setup", "softap", "system", "time", "ntp")
        settings = "\n".join(command(host, f"get {g}") for g in groups)
    (out / "settings.txt").write_text(settings + "\n")
    print("  saved settings.txt")
    print(f"""
Backup saved in {out}/. File contents are not copied: reading binary files
over the API crashes the module. The only file this setup replaces is the
trusted CA, which is the public Baltimore CyberTrust Root. To undo the
setup, upload that certificate in DER form under the same name.""")


def step_join(args: argparse.Namespace) -> None:
    """In setup mode: join the faucet to your Wi-Fi and enable its HTTP API there."""
    pause(
        "Put the faucet in Wi-Fi setup mode. A faucet with no saved Wi-Fi starts in\n"
        "it on its own, and the module's LED blinks green. Then join this computer to\n"
        "the Wi-Fi network named 'ZentriOS Web Setup' followed by three letters or\n"
        "digits (the end of the faucet's MAC address). Its password is usually\n"
        "'password'. Your computer will lose internet access while it is joined."
    )
    host = SETUP_IP
    wait_for(host, "setup mode")
    if not args.skip_backup:
        step_backup(argparse.Namespace(**{**vars(args), "host": host}))
    print("\nThe faucet needs 2.4 GHz Wi-Fi. A separate IoT network or VLAN is a good idea.")
    ssid = args.ssid or input("Wi-Fi network name (SSID): ").strip()
    passkey = getpass.getpass("Wi-Fi password (not shown): ")
    settings = [
        ("hide the password in settings output", "set wlan.hide_passkey 1"),
        ("Wi-Fi network", f'set wlan.ssid "{ssid}"'),
        ("Wi-Fi password", f'set wlan.passkey "{passkey}"'),
        ("hostname", f"set wlan.dhcp.hostname {args.hostname}"),
        ("DHCP", "set wlan.dhcp.enabled 1"),
        ("join automatically", "set wlan.auto_join.enabled 1"),
        ("HTTP server", "set http.server.enabled 1"),
        ("HTTP command API", "set http.server.api_enabled 1"),
        ("serve HTTP on Wi-Fi", "set http.server.interface wlan"),
        ("save", "save"),
    ]
    for label, cmd in settings:
        command(host, cmd)
        print(f"  {label}: done")
    del passkey
    with contextlib.suppress(OSError, FaucetError):  # the connection drops as it restarts
        command(host, "reboot", timeout=3)
    print(f"""
Saved and restarting. The faucet leaves setup mode and joins '{ssid}'.

Now:
  1. Rejoin this computer to your normal network.
  2. Find the faucet's IP address in your router's client list (hostname
     '{args.hostname}'). A DHCP reservation keeps it stable.
Then run:  python3 {sys.argv[0]} upload --host <faucet IP>""")


def _local_ip_towards(host: str) -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((host, 80))
        return str(s.getsockname()[0])


def _serve(directory: Path, port: int) -> http.server.ThreadingHTTPServer:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _size_on_module(host: str, name: str) -> int | None:
    for line in command(host, "ls -v").splitlines():
        parts = line.split()
        if parts and parts[-1] == name:
            # "#  type  flags  hnd  size  version  name"; size is the first all-digit field after the handle
            nums = [p for p in parts[1:-1] if p.isdigit()]
            return int(nums[-1]) if nums else None
    return None


def step_upload(args: argparse.Namespace) -> None:
    """On your LAN: replace the faucet's trusted CA file with your ca.der."""
    if not args.host:
        sys.exit("Give the faucet's LAN address with --host.")
    host = args.host
    ca = Path(args.pki) / "ca.der"
    if not ca.exists():
        sys.exit(f"{ca} is missing. Run the certs step first.")
    wait_for(host, "on your network")
    target = command(host, "get network.tls.ca_cert").split()[0]
    print(f"The faucet trusts the CA in '{target}'. Its controller sets that name at every boot,")
    print("so the file keeps its name and only its contents change.")

    me = args.serve_ip or _local_ip_towards(host)
    server = _serve(ca.parent, args.port)
    url = f"http://{me}:{args.port}/ca.der"
    print(f"Serving {ca} at {url}")
    print("The faucet downloads it from this computer, so its network must be able to reach")
    print(
        f"this one on port {args.port}. If the download fails, see 'Uploading the CA' in docs/SETUP.md."
    )
    try:
        wait_for_fresh_boot(host)
        staging = "local-ca.der"
        with contextlib.suppress(FaucetError):  # no leftover from an earlier run
            command(host, f"fde {staging}")
        command(host, f"hdo {url} {staging}", timeout=40)
        size = _size_on_module(host, staging)
        if size != ca.stat().st_size:
            sys.exit(
                f"Test download came out {size} bytes, expected {ca.stat().st_size}. Nothing replaced."
            )
        print("  test download OK")
        command(host, f"fde {staging}")
        command(host, f"fde {target}")
        command(host, f"hdo {url} {target}", timeout=40)
        size = _size_on_module(host, target)
        if size != ca.stat().st_size:
            sys.exit(
                f"{target} came out {size} bytes. Run this step again before restarting the faucet."
            )
        print(f"  {target} replaced with your CA ({size} bytes)")
    finally:
        server.shutdown()
    print(
        """
Done. Before the faucet can connect, two things must be true (docs/SETUP.md):
  1. Your router's DNS answers the Azure hub name with your broker's address.
  2. Your broker has a TLS listener on 8883 using server.pem and server.key,
     allowing TLS 1.0 and the ECDHE-RSA-AES256-SHA cipher.
Then run:  python3 """
        + sys.argv[0]
        + f" verify --host {host}"
    )


def step_verify(args: argparse.Namespace) -> None:
    """Watch the module's uptime. Restarts every ~42 s mean it still can't connect."""
    if not args.host:
        sys.exit("Give the faucet's LAN address with --host.")
    host = args.host
    wait_for(host, "on your network")
    try:
        print(f"DNS on this computer: {args.hub} -> {socket.gethostbyname(args.hub)}")
    except OSError:
        print(f"DNS on this computer: {args.hub} does not resolve")
    print("Watching for 3 minutes. Uptime that keeps climbing past 60 s means it connected.")
    best = 0
    end = time.monotonic() + 180
    while time.monotonic() < end:
        up = uptime(host)
        if up is not None:
            best = max(best, up)
            print(f"  uptime {up:>4} s", flush=True)
            if up > 120:
                print("Connected: the module has stayed up for over 2 minutes.")
                return
        time.sleep(10)
    print(
        f"Still restarting (longest uptime {best} s). Check DNS, the broker's TLS settings, and its logs."
    )


def step_all(args: argparse.Namespace) -> None:
    print(__doc__)
    if not (Path(args.pki) / "ca.der").exists():
        step_certs(args)
    pause("Next: Wi-Fi setup. This step needs the faucet in setup mode.")
    step_join(args)
    args.host = args.host or input("\nFaucet IP address on your network: ").strip()
    step_upload(args)
    pause("Set up the router DNS override and the broker listener now (docs/SETUP.md).")
    step_verify(args)


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "step",
        nargs="?",
        default="all",
        choices=["all", "certs", "backup", "join", "upload", "verify"],
    )
    p.add_argument("--host", help="faucet address on your LAN (setup mode is always 10.10.10.1)")
    p.add_argument(
        "--pki",
        default="faucet-pki",
        help="folder for the CA and certificates (default: faucet-pki)",
    )
    p.add_argument("--backup", help="folder for the backup (default: faucet-backup-<time>)")
    p.add_argument(
        "--hub",
        default=DEFAULT_HUB,
        help=f"Azure IoT hub name the faucet dials (default: {DEFAULT_HUB})",
    )
    p.add_argument("--ssid", help="Wi-Fi network for the faucet to join")
    p.add_argument("--hostname", default="delta-faucet", help="DHCP hostname for the faucet")
    p.add_argument(
        "--skip-backup", action="store_true", help="skip the backup during the join step"
    )
    p.add_argument(
        "--port", type=int, default=8765, help="port to serve ca.der from (default: 8765)"
    )
    p.add_argument(
        "--serve-ip", help="address the faucet should download ca.der from (default: auto)"
    )
    args = p.parse_args()
    {
        "all": step_all,
        "certs": step_certs,
        "backup": step_backup,
        "join": step_join,
        "upload": step_upload,
        "verify": step_verify,
    }[args.step](args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nStopped.")
    except FaucetError as error:
        sys.exit(f"The faucet refused a command: {error}")
