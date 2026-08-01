#!/usr/bin/env bash
#
# Öffnet ein Zeitfenster (120 Sekunden), in dem sich ein Handy/Tablet
# per Bluetooth mit XRack koppeln kann, und schaltet Koppelbarkeit
# danach automatisch wieder aus.
#
# Wird ausschließlich per sudo durch XRack selbst aufgerufen (siehe
# core/bluetooth_control.py), nie interaktiv. Keine Argumente.
#

set -e

DURATION=120

bluetoothctl power on >/dev/null
bluetoothctl discoverable on >/dev/null
bluetoothctl pairable on >/dev/null

# Wie bei xrack-restart.sh: als eigenständige, vom aufrufenden
# Prozess unabhängige Einheit planen, damit das Abschalten auch dann
# zuverlässig passiert, wenn der auslösende sudo-Aufruf längst beendet
# ist.
systemd-run --on-active="${DURATION}" --unit="xrack-bt-pair-timeout-$$" \
    /bin/sh -c 'bluetoothctl discoverable off; bluetoothctl pairable off' \
    >/dev/null
