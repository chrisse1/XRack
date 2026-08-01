#!/usr/bin/env bash
#
# Schaltet den Bluetooth-Adapter an oder aus.
#
# Wird ausschließlich per sudo durch XRack selbst aufgerufen (siehe
# core/bluetooth_control.py), nie interaktiv. $1 = "on" oder "off".
#

set -e

MODE="$1"

if [ "${MODE}" != "on" ] && [ "${MODE}" != "off" ]; then
    echo "Ungültiger Modus (on/off erwartet)." >&2
    exit 1
fi

bluetoothctl power "${MODE}" >/dev/null

if [ "${MODE}" = "off" ]; then
    bluetoothctl discoverable off >/dev/null 2>&1 || true
    bluetoothctl pairable off >/dev/null 2>&1 || true
fi
