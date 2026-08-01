#!/usr/bin/env bash
#
# Schaltet die Ethernet+Access-Point-Bridge ("XRack-Bridge", siehe
# install.sh) an oder aus. Setzt voraus, dass sie schon einmal per
# install.sh eingerichtet wurde - baut sie nicht neu auf.
#
# Wird ausschließlich per sudo durch XRack selbst aufgerufen (siehe
# core/wlan_control.py), nie interaktiv. $1 = "on" oder "off".
#

set -e

MODE="$1"

if ! nmcli -t -f NAME connection show | grep -qx "XRack-AP"; then
    echo "XRack-AP ist nicht eingerichtet (install.sh mit WLAN-Setup ausführen)." >&2
    exit 1
fi

AP_IFACE="$(nmcli -g connection.interface-name connection show "XRack-AP")"

# Das gespeicherte AP-Passwort wird beim Umhängen von master/slave-
# type nicht verlässlich beibehalten - deshalb hier vorher auslesen
# (root darf das, "nmcli -s") und bei jeder modify-Aktion explizit
# wieder mitsetzen.
CURRENT_PSK="$(nmcli -s -g 802-11-wireless-security.psk connection show "XRack-AP")"

if [ "${MODE}" = "on" ]; then

    if ! nmcli -t -f NAME connection show | grep -qx "XRack-Bridge"; then
        echo "XRack-Bridge ist nicht eingerichtet (install.sh mit WLAN+Bridge-Setup ausführen)." >&2
        exit 1
    fi

    ETH0_CON="$(nmcli -t -f NAME,DEVICE connection show | awk -F: '$2=="eth0"{print $1; exit}')"

    if [ -n "${ETH0_CON}" ] && [ "${ETH0_CON}" != "XRack-Bridge-eth0" ]; then
        nmcli connection modify "${ETH0_CON}" connection.autoconnect no
    fi

    nmcli connection modify "XRack-AP" \
        master "XRack-Bridge" slave-type bridge \
        wifi-sec.psk "${CURRENT_PSK}" wifi-sec.psk-flags 0 \
        connection.autoconnect yes

    nmcli connection modify "XRack-Bridge-eth0" connection.autoconnect yes
    nmcli connection modify "XRack-Bridge" connection.autoconnect yes

    nmcli connection up "XRack-Bridge"
    nmcli connection up "XRack-Bridge-eth0" ifname eth0
    nmcli connection up "XRack-AP" ifname "${AP_IFACE}"

elif [ "${MODE}" = "off" ]; then

    nmcli connection modify "XRack-AP" \
        connection.master "" \
        connection.slave-type "" \
        ipv4.method shared \
        wifi-sec.psk "${CURRENT_PSK}" wifi-sec.psk-flags 0 \
        connection.autoconnect yes

    nmcli connection down "XRack-Bridge" >/dev/null 2>&1 || true
    nmcli connection modify "XRack-Bridge-eth0" connection.autoconnect no
    nmcli connection modify "XRack-Bridge" connection.autoconnect no

    nmcli connection up "XRack-AP" ifname "${AP_IFACE}"

else
    echo "Unbekannter Modus: ${MODE} (erwartet: on oder off)" >&2
    exit 1
fi
