#!/usr/bin/env bash
#
# Entfernt alle gekoppelten Bluetooth-Geräte, damit sich ein neues
# Handy/Tablet koppeln kann.
#
# Wird ausschließlich per sudo durch XRack selbst aufgerufen (siehe
# core/bluetooth_control.py), nie interaktiv. Keine Argumente.
#

set -e

bluetoothctl devices Paired | awk '{print $2}' | while read -r mac; do
    [ -n "${mac}" ] && bluetoothctl remove "${mac}" >/dev/null 2>&1 || true
done
