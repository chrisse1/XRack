#!/usr/bin/env bash
#
# Setzt SSID/Passwort des Access Points ("XRack-AP", siehe
# install.sh) neu und startet ihn neu.
#
# Wird ausschließlich per sudo durch XRack selbst aufgerufen (siehe
# core/wlan_control.py), nie interaktiv. $1 = SSID, $2 = Passwort.
#

set -e

SSID="$1"
PASSWORD="$2"

if [ -z "${SSID}" ] || [ "${#PASSWORD}" -lt 8 ]; then
    echo "SSID fehlt oder Passwort zu kurz (mind. 8 Zeichen)." >&2
    exit 1
fi

if ! nmcli -t -f NAME connection show | grep -qx "XRack-AP"; then
    echo "XRack-AP ist nicht eingerichtet (install.sh mit WLAN-Setup ausführen)." >&2
    exit 1
fi

IFACE="$(nmcli -g connection.interface-name connection show "XRack-AP")"

nmcli connection modify "XRack-AP" \
    802-11-wireless.ssid "${SSID}" \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.proto rsn \
    wifi-sec.psk "${PASSWORD}" \
    wifi-sec.psk-flags 0 \
    connection.autoconnect yes

nmcli connection up "XRack-AP" ifname "${IFACE}"
