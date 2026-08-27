#!/usr/bin/env bash
#
# Setzt SSID/Passwort der Heimnetz-Client-Verbindung ("XRack-Home",
# siehe install.sh) neu und verbindet sich damit.
#
# Ist noch gar keine eingerichtet, wird sie hier angelegt - so lässt
# sich die WLAN-Verbindung jederzeit nachrüsten, ohne install.sh
# erneut laufen zu lassen.
#
# Wird ausschließlich per sudo durch XRack selbst aufgerufen (siehe
# core/wlan_control.py), nie interaktiv.
#
#   $1 = SSID, $2 = Passwort, $3 = Funkregion (optional)
#   --country XX   nur die Funkregion setzen, sonst nichts
#
# Die Funkregion hängt hier mit dran, weil sie über den vorhandenen
# sudoers-Eintrag laufen muss (siehe scripts/xrack-wifi-country.sh) -
# ein eigener Eintrag entstünde erst bei einem erneuten Lauf von
# install.sh.
#

set -e

LAND_SKRIPT="$(dirname "$0")/xrack-wifi-country.sh"

#
# Nur die Funkregion setzen. Das ist der Weg für jemanden, der bei der
# Installation weder WLAN noch Access Point eingerichtet hat: Ohne
# Region bleibt das Funkgerät gesperrt, und dann liefe auch das
# Anlegen einer Verbindung ins Leere.
#
if [ "$1" = "--country" ]; then
    exec "${LAND_SKRIPT}" "$2"
fi

SSID="$1"
PASSWORD="$2"
COUNTRY="$3"

if [ -z "${SSID}" ] || [ "${#PASSWORD}" -lt 8 ]; then
    echo "SSID fehlt oder Passwort zu kurz (mind. 8 Zeichen)." >&2
    exit 1
fi

#
# Region vor dem Verbinden setzen, nicht danach: Ein per rfkill
# gesperrtes Funkgerät nimmt die Verbindung gar nicht erst an.
#
if [ -n "${COUNTRY}" ]; then
    "${LAND_SKRIPT}" "${COUNTRY}" || true
fi

#
# Gibt es das Profil noch nicht, wird es hier angelegt - der
# Nachruestfall. Wer bei der Installation "keine WLAN-Verbindung"
# gewählt hat, soll sie später im Einstellungen-Menü einrichten
# können, ohne install.sh erneut laufen zu lassen.
#
if ! nmcli -t -f NAME connection show | grep -qx "XRack-Home"; then

    IFACE="$("$(dirname "$0")/xrack-wifi-iface.sh" client)"

    if [ -z "${IFACE}" ]; then
        echo "Kein WLAN-Gerät gefunden." >&2
        exit 1
    fi

    nmcli connection add type wifi ifname "${IFACE}" con-name "XRack-Home" \
        ssid "${SSID}" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "${PASSWORD}" \
        connection.autoconnect yes >/dev/null || exit 1
fi

#
# Vor dem Auslesen abgleichen: Im Profil kann ein Geraetename stehen,
# der seit dem letzten Booten einem anderen Funkgeraet gehoert (siehe
# xrack-wifi-bind.sh). Ungeprueft weiterverwendet, wuerde die
# Heimnetz-Verbindung auf dem USB-Stick landen.
#
"$(dirname "$0")/xrack-wifi-bind.sh" || true

IFACE="$(nmcli -g connection.interface-name connection show "XRack-Home")"

nmcli connection modify "XRack-Home" \
    802-11-wireless.ssid "${SSID}" \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "${PASSWORD}" \
    wifi-sec.psk-flags 0 \
    connection.autoconnect yes

# Ist die Verbindung bereits aktiv, übernimmt ein reines "connection
# up" SSID/Passwort-Änderungen nicht zuverlässig live - deshalb hier
# ausdrücklich erst trennen, dann mit den neuen Werten neu verbinden.
nmcli connection down "XRack-Home" >/dev/null 2>&1 || true

nmcli connection up "XRack-Home" ifname "${IFACE}"
