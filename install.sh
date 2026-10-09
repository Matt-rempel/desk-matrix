#!/bin/sh
# Install or update Desk Matrix on Raspberry Pi OS Lite. Run as a login user.
set -eu

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
CODE_DIR=/opt/flightboard
STATE_DIR=/var/lib/flightboard
DRIVER_COMMIT=51d3231e370593b60952b2c3b18d2e3802329f18
SHOW_PAIRING=1

if [ "${1:-}" = "--no-pairing-link" ] && [ "$#" -eq 1 ]; then
  SHOW_PAIRING=0
elif [ "$#" -ne 0 ]; then
  printf 'Usage: sh install.sh [--no-pairing-link]\n' >&2
  exit 2
fi
if [ "$(id -u)" -eq 0 ]; then
  printf 'Run this as your normal Pi user, without sudo. The script asks for sudo when needed.\n' >&2
  exit 1
fi
if [ ! -r /proc/device-tree/model ] || ! grep -aq 'Raspberry Pi' /proc/device-tree/model; then
  printf 'This installer runs on a Raspberry Pi, not on your laptop.\n' >&2
  exit 1
fi
if ! command -v apt-get >/dev/null 2>&1 || ! command -v systemctl >/dev/null 2>&1; then
  printf 'Raspberry Pi OS or another Debian system with systemd is required.\n' >&2
  exit 1
fi
for file in flightboard.py settings.py screens.py web_server.py index.html app.css app.js flightboard.service flightboard-web.service; do
  if [ ! -f "$SOURCE_DIR/$file" ]; then
    printf 'Missing %s; run the installer from a complete checkout.\n' "$file" >&2
    exit 1
  fi
done

sudo -v
printf '\nInstalling Raspberry Pi build packages…\n'
sudo apt-get update
sudo apt-get install -y curl git build-essential cmake python3-dev python3-venv python3-setuptools python3-wheel cython3

if ! id flightboard >/dev/null 2>&1; then
  sudo useradd --system --user-group --home-dir "$STATE_DIR" --shell /usr/sbin/nologin flightboard
fi
sudo install -d -o root -g root -m 0755 "$CODE_DIR"
sudo install -d -o flightboard -g flightboard -m 0700 "$STATE_DIR"

if [ ! -x "$CODE_DIR/.venv/bin/python" ]; then
  printf '\nCreating the Python environment…\n'
  sudo python3 -m venv --system-site-packages "$CODE_DIR/.venv"
fi
if ! "$CODE_DIR/.venv/bin/python" -c 'import rgbmatrix' >/dev/null 2>&1; then
  printf '\nBuilding the matrix driver. This may take several minutes on a Pi 3…\n'
  sudo env CMAKE_BUILD_PARALLEL_LEVEL=2 "$CODE_DIR/.venv/bin/python" -m pip install --no-input \
    "git+https://github.com/hzeller/rpi-rgb-led-matrix@$DRIVER_COMMIT"
fi

if ! command -v tailscale >/dev/null 2>&1; then
  printf '\nInstalling Tailscale…\n'
  installer=$(mktemp)
  curl -fsSL https://tailscale.com/install.sh -o "$installer"
  sudo sh "$installer"
  rm -f "$installer"
fi
tail_state=$(tailscale status --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("BackendState", ""))' 2>/dev/null || true)
if [ "$tail_state" != Running ]; then
  printf '\nSign the Pi in to Tailscale using the link below.\n'
  sudo tailscale up
fi
tail_state=$(tailscale status --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("BackendState", ""))' 2>/dev/null || true)
if [ "$tail_state" != Running ]; then
  printf 'Tailscale sign-in is pending. Finish it and rerun sh install.sh.\n' >&2
  exit 1
fi
printf '\nEnabling private HTTPS for the settings page…\n'
sudo tailscale serve --bg --https=443 8765
if ! tailscale serve status | grep -Fq 'proxy http://127.0.0.1:8765'; then
  printf 'Tailscale Serve is not ready. Approve its browser link and rerun sh install.sh.\n' >&2
  exit 1
fi
dns_name=$(tailscale status --json | python3 -c 'import json,sys; print((json.load(sys.stdin).get("Self") or {}).get("DNSName", "").rstrip("."))')
if [ -z "$dns_name" ]; then
  printf 'Tailscale did not return a DNS name. Installation stopped before switching services.\n' >&2
  exit 1
fi

# Back up the small application files and units. The virtual environment and
# saved settings stay in place across updates.
backup=$(mktemp -d)
for file in flightboard.py settings.py screens.py web_server.py index.html app.css app.js; do
  if [ -f "$CODE_DIR/$file" ]; then cp -p "$CODE_DIR/$file" "$backup/$file"; fi
done
for unit in flightboard.service flightboard-web.service; do
  if [ -f "/etc/systemd/system/$unit" ]; then cp -p "/etc/systemd/system/$unit" "$backup/$unit"; fi
done
rollback=1
on_exit() {
  result=$1
  trap - EXIT
  if [ "$result" -ne 0 ] && [ "$rollback" -eq 1 ]; then
    printf '\nInstall failed; restoring the previous application and services.\n' >&2
    for file in flightboard.py settings.py screens.py web_server.py index.html app.css app.js; do
      if [ -f "$backup/$file" ]; then
        sudo install -o root -g root -m 0644 "$backup/$file" "$CODE_DIR/$file"
      else
        sudo rm -f "$CODE_DIR/$file"
      fi
    done
    for unit in flightboard.service flightboard-web.service; do
      if [ -f "$backup/$unit" ]; then
        sudo install -o root -g root -m 0644 "$backup/$unit" "/etc/systemd/system/$unit"
      else
        sudo systemctl disable --now "$unit" 2>/dev/null || true
        sudo rm -f "/etc/systemd/system/$unit"
      fi
    done
    sudo systemctl daemon-reload
    for unit in flightboard-web.service flightboard.service; do
      if [ -f "$backup/$unit" ]; then sudo systemctl restart "$unit" || true; fi
    done
  fi
  rm -rf "$backup"
  exit "$result"
}
trap 'on_exit $?' EXIT

for file in flightboard.py settings.py screens.py web_server.py index.html app.css app.js; do
  sudo install -o root -g root -m 0644 "$SOURCE_DIR/$file" "$CODE_DIR/$file"
done
sudo chown -hR root:root "$CODE_DIR"
sudo chmod -R go-w "$CODE_DIR"
printf '%s\n' "$dns_name" | sudo tee "$STATE_DIR/public-host" >/dev/null
sudo chown root:root "$STATE_DIR/public-host"
sudo chmod 0644 "$STATE_DIR/public-host"
if [ ! -f "$STATE_DIR/web-token" ]; then
  token=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
  printf '%s\n' "$token" | sudo tee "$STATE_DIR/web-token" >/dev/null
fi
sudo chown flightboard:flightboard "$STATE_DIR/web-token"
sudo chmod 0600 "$STATE_DIR/web-token"
sudo -u flightboard test ! -w "$CODE_DIR/flightboard.py"
sudo -u flightboard test -w "$STATE_DIR"
sudo -u flightboard env FLIGHTBOARD_STATE_DIR="$STATE_DIR" \
  "$CODE_DIR/.venv/bin/python" -c 'import sys; sys.path.insert(0,"/opt/flightboard"); import rgbmatrix, flightboard, web_server; from settings import Settings,validate_settings; validate_settings(Settings().to_dict())'

for unit in flightboard.service flightboard-web.service; do
  sudo install -o root -g root -m 0644 "$SOURCE_DIR/$unit" "/etc/systemd/system/$unit"
done
sudo systemctl daemon-reload
sudo systemctl enable flightboard.service flightboard-web.service
sudo systemctl restart flightboard-web.service flightboard.service
sleep 3
systemctl is-active --quiet flightboard-web.service
systemctl is-active --quiet flightboard.service
curl --connect-timeout 3 --max-time 5 -fsS http://127.0.0.1:8765/ -o /dev/null
rollback=0

printf '\nDesk Matrix is running. Settings: https://%s/\n' "$dns_name"
if [ "$SHOW_PAIRING" -eq 1 ]; then
  token=$(sudo cat "$STATE_DIR/web-token")
  printf 'Private pairing link (keep it out of screenshots and chat):\nhttps://%s/#%s\n' "$dns_name" "$token"
else
  printf 'Pairing link hidden. Retrieve the key on the Pi with sudo cat %s/web-token.\n' "$STATE_DIR"
fi
printf 'Set your location and time zone on the settings page.\n'
