#!/usr/bin/env bash
#
# Entfernt ein einzelnes gekoppeltes Bluetooth-Gerät.
#
# Wird ausschließlich per sudo durch XRack selbst aufgerufen (siehe
# core/bluetooth_control.py), nie interaktiv. $1 = MAC-Adresse.
#

set -e

MAC="$1"

if ! [[ "${MAC}" =~ ^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$ ]]; then
    echo "Ungültige MAC-Adresse." >&2
    exit 1
fi

bluetoothctl remove "${MAC}"
