#!/usr/bin/env bash
#
# Schaltet die Ethernet+Access-Point-Bridge ("XRack-Bridge", siehe
# install.sh) an oder aus. Setzt voraus, dass sie schon einmal per
# install.sh eingerichtet wurde - baut sie nicht neu auf.
#
# Schließt sich mit der Ethernet+Heimnetz-Freigabe aus (beide
# beanspruchen eth0) - deshalb wird hier die Freigabe mit
# abgeschaltet, falls aktiv.
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

    #
    # Exklusiv zur Ethernet+Heimnetz-Freigabe - beide wollen eth0 für
    # sich.
    #
    if nmcli -t -f NAME connection show --active | grep -qx "XRack-Share-eth0"; then
        nmcli connection down "XRack-Share-eth0" >/dev/null 2>&1 || true
    fi

    nmcli connection modify "XRack-Share-eth0" connection.autoconnect no 2>/dev/null || true

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

    # War der Access Point bereits aktiv (Standalone-Betrieb), reicht
    # ein reines "connection up" nach dem Umhängen auf die Bridge oft
    # nicht - erst herunterfahren erzwingt einen sauberen Neustart mit
    # der neuen master/slave-Konfiguration.
    nmcli connection down "XRack-AP" >/dev/null 2>&1 || true
    nmcli connection up "XRack-AP" ifname "${AP_IFACE}"

    #
    # Das Pult zum erneuten DHCP bewegen: Es liegt jetzt in einem
    # anderen Netz, merkt davon aber nichts, solange die Verbindung
    # durchgehend bestand. Siehe xrack-link-bounce.sh.
    #
    BOUNCE="$(dirname "$0")/xrack-link-bounce.sh"

    if [ -x "${BOUNCE}" ]; then
        "${BOUNCE}" eth0 || true
    fi

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

    nmcli connection down "XRack-AP" >/dev/null 2>&1 || true
    nmcli connection up "XRack-AP" ifname "${AP_IFACE}"

else
    echo "Unbekannter Modus: ${MODE} (erwartet: on oder off)" >&2
    exit 1
fi
