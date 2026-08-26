#!/usr/bin/env bash
#
# Gibt den Namen (SSID) des eingerichteten Access Points aus - eine
# Zeile, sonst nichts.
#
# Warum als eigenes Skript mit sudo: Seit der Access Point über
# hostapd läuft, steht die SSID in /etc/hostapd/xrack.conf. Diese
# Datei enthält auch das WLAN-Passwort im Klartext und ist deshalb
# nur für root lesbar. XRack selbst läuft nicht als root und kann
# sie also nicht einfach aufmachen.
#
# Auf Geräten mit dem alten NetworkManager-Weg wird die SSID aus dem
# Profil "XRack-AP" gelesen.
#
# Wird ausschließlich per sudo durch XRack selbst aufgerufen (siehe
# core/wlan_control.py), nie interaktiv. Keine Argumente.
#

set -e

CONF="/etc/hostapd/xrack.conf"

if [ -r "${CONF}" ]; then

    #
    # Die erste ssid=-Zeile gewinnt; alles nach dem ersten
    # Gleichheitszeichen gehört zum Namen (SSIDs dürfen "=" und
    # Leerzeichen enthalten).
    #
    sed -n 's/^ssid=//p' "${CONF}" | head -n 1
    exit 0
fi

if command -v nmcli >/dev/null 2>&1 \
   && nmcli -t -f NAME connection show | grep -qx "XRack-AP"; then

    nmcli -g 802-11-wireless.ssid connection show "XRack-AP"
fi
