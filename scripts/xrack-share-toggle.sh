#!/usr/bin/env bash
#
# Schaltet die Ethernet+Heimnetz-Freigabe ("XRack-Share-eth0", siehe
# install.sh) an oder aus. Setzt voraus, dass sie schon einmal per
# install.sh eingerichtet wurde - baut sie nicht neu auf.
#
# Anders als die Ethernet+Access-Point-Bridge (xrack-bridge-toggle.sh)
# ist das hier KEINE echte Layer-2-Bridge: Eine WLAN-Verbindung im
# Client-Modus (XRack-Home) kann fremde MAC-Adressen normalerweise
# nicht transparent durchschleifen (dafür bräuchte es 4-Adress-WDS,
# das die meisten Heim-Router nicht unterstützen). Stattdessen bekommt
# eth0 hier per NetworkManager "ipv4.method shared" eine eigene
# IP-Range mit NAT/DHCP-Server - Geräte am LAN-Port bekommen also eine
# eigene IP von XRack, haben darüber aber vollen Zugriff auf das, was
# über die aktuell aktive Verbindung (z.B. XRack-Home) erreichbar ist.
#
# Schließt sich mit der Ethernet+AP-Bridge aus (beide beanspruchen
# eth0) - deshalb wird eth0 hier aus der Bridge genommen, falls es
# darin hängt. Der Access Point selbst bleibt dabei unangetastet: Er
# hängt dauerhaft in br0 und funkt weiter, egal wohin eth0 gerade
# gehört.
#
# Wird ausschließlich per sudo durch XRack selbst aufgerufen (siehe
# core/wlan_control.py), nie interaktiv. $1 = "on" oder "off".
#

set -e

MODE="$1"

if [ "${MODE}" = "on" ]; then

    if ! nmcli -t -f NAME connection show | grep -qx "XRack-Share-eth0"; then
        echo "XRack-Share-eth0 ist nicht eingerichtet (install.sh mit WLAN-Setup ausführen)." >&2
        exit 1
    fi

    #
    # Exklusiv zur Ethernet+AP-Bridge - beide wollen eth0 für sich.
    #
    nmcli connection down "XRack-Bridge-eth0" >/dev/null 2>&1 || true
    nmcli connection modify "XRack-Bridge-eth0" connection.autoconnect no 2>/dev/null || true

    #
    # Jetzt hat die Bridge keinen von NetworkManager verwalteten
    # Anschluss mehr - der Access Point gehört hostapd. Genau hier
    # nachsehen, ob sie ihre Adresse behält: Verliert sie sie, ist mit
    # ihr der DHCP-Server weg, und das fällt erst auf, wenn beim
    # Zurückschalten niemand mehr antwortet. Siehe
    # xrack-bridge-ensure.sh.
    #
    ENSURE="$(dirname "$0")/xrack-bridge-ensure.sh"

    if [ -x "${ENSURE}" ]; then
        "${ENSURE}" || true
    fi

    #
    # Die normale Kabelverbindung stilllegen, solange die Freigabe
    # läuft - sonst holt sie sich eth0 beim nächsten Start zurück.
    #
    nmcli connection down "XRack-Wired-eth0" >/dev/null 2>&1 || true
    nmcli connection modify "XRack-Wired-eth0" connection.autoconnect no 2>/dev/null || true

    ETH0_CON="$(nmcli -t -f NAME,DEVICE connection show | awk -F: '$2=="eth0"{print $1; exit}')"

    if [ -n "${ETH0_CON}" ] && [ "${ETH0_CON}" != "XRack-Share-eth0" ]; then
        nmcli connection modify "${ETH0_CON}" connection.autoconnect no
    fi

    nmcli connection modify "XRack-Share-eth0" connection.autoconnect yes

    nmcli connection down "XRack-Share-eth0" >/dev/null 2>&1 || true
    nmcli connection up "XRack-Share-eth0" ifname eth0

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

    nmcli connection down "XRack-Share-eth0" >/dev/null 2>&1 || true
    nmcli connection modify "XRack-Share-eth0" connection.autoconnect no 2>/dev/null || true

    #
    # Zurück in den Normalbetrieb - ohne das bliebe die Buchse ohne
    # aktives Profil liegen. Siehe xrack-wired-restore.sh.
    #
    ZURUECK="$(dirname "$0")/xrack-wired-restore.sh"

    if [ -x "${ZURUECK}" ]; then
        "${ZURUECK}" || true
    fi

else
    echo "Unbekannter Modus: ${MODE} (erwartet: on oder off)" >&2
    exit 1
fi
