#!/usr/bin/env bash
#
# Trennt die Verbindung zu einem gekoppelten Bluetooth-Gerät, ohne
# die Kopplung selbst aufzuheben (das Gerät bleibt gekoppelt und kann
# sich später wieder von selbst verbinden).
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

bluetoothctl disconnect "${MAC}"
