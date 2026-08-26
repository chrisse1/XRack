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
# eth0) - deshalb wird hier die Bridge mit abgeschaltet, falls aktiv.
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
    # Die Bridge wird über ihr eigenes Skript abgeschaltet statt hier
    # nachgebaut. Das ist nicht nur weniger Doppelung, sondern behebt
    # einen Fehler: Beim Einschalten hängt die Bridge den Access Point
    # als Slave ein ("master XRack-Bridge"). Wer das nur teilweise
    # zurückdreht - Bridge runter, Access Point aber weiter als Slave
    # konfiguriert -, hinterlässt zwei Probleme:
    #
    #   1. Der Access Point gehört zu einer Bridge, die nicht mehr
    #      läuft, und funktioniert bis zum nächsten Neustart nicht.
    #
    #   2. Schlimmer: Beim Hochfahren zieht NetworkManager mit einem
    #      Slave immer auch dessen Master hoch - ganz unabhängig davon,
    #      ob der Master "autoconnect no" hat. Nach einem Neustart wären
    #      Bridge UND Freigabe aktiv, obwohl sie sich ausschließen.
    #
    # "xrack-bridge-toggle.sh off" macht genau das Richtige: Es löst
    # den Access Point wieder heraus und stellt ihn eigenständig wieder
    # her.
    #
    BRIDGE_TOGGLE="$(dirname "$0")/xrack-bridge-toggle.sh"

    if [ -x "${BRIDGE_TOGGLE}" ] \
       && nmcli -t -f NAME connection show | grep -qx "XRack-AP"; then

        #
        # Kein sudo: Dieses Skript läuft bereits als root.
        # Ein Fehlschlag darf die Freigabe nicht verhindern - im
        # Zweifel ist eine laufende Freigabe wichtiger als eine
        # aufgeräumte Bridge.
        #
        "${BRIDGE_TOGGLE}" off || true

    else

        #
        # Kein Access Point eingerichtet: Dann gibt es auch keinen
        # Slave, der zurückgedreht werden müsste.
        #
        nmcli connection down "XRack-Bridge" >/dev/null 2>&1 || true
        nmcli connection modify "XRack-Bridge-eth0" connection.autoconnect no 2>/dev/null || true
        nmcli connection modify "XRack-Bridge" connection.autoconnect no 2>/dev/null || true

    fi

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

else
    echo "Unbekannter Modus: ${MODE} (erwartet: on oder off)" >&2
    exit 1
fi
