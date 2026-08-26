#!/usr/bin/env bash
#
# Hängt das Ethernet-Interface (Mischpult an eth0) in die Bridge br0
# ein oder wieder aus - das ist die Einstellung "Konsole über XRacks
# Access Point erreichbar machen".
#
# Der Access Point selbst hängt dauerhaft in derselben Bridge und
# wird hier NICHT angefasst (siehe den Kommentarblock zum Access
# Point in install.sh). Genau das war vorher anders: Da wurde der
# Access Point beim Umschalten zum Bridge-Slave umkonfiguriert und
# neu gestartet. Daraus entstanden zwei Fehlerbilder, die es jetzt
# nicht mehr geben kann:
#
#   1. Nach dem Umschalten war ein Neustart nötig, weil der Access
#      Point mit der neuen Master/Slave-Konfiguration nicht sauber
#      wieder hochkam.
#
#   2. Nach einem Neustart waren beide Betriebsarten gleichzeitig an,
#      weil NetworkManager mit einem Slave immer auch dessen Master
#      hochzieht - unabhängig davon, ob der Master "autoconnect no"
#      hat.
#
# Schließt sich weiterhin mit der Ethernet+Heimnetz-Freigabe aus
# (beide beanspruchen eth0) - deshalb wird die Freigabe hier
# abgeschaltet, falls aktiv.
#
# Wird ausschließlich per sudo durch XRack selbst aufgerufen (siehe
# core/wlan_control.py), nie interaktiv. $1 = "on" oder "off".
#

set -e

MODE="$1"

if ! nmcli -t -f NAME connection show | grep -qx "XRack-Bridge-eth0"; then
    echo "XRack-Bridge-eth0 ist nicht eingerichtet (install.sh mit WLAN-Setup ausführen)." >&2
    exit 1
fi

#
# br0 trägt die IP-Adresse, den DHCP-Server und die
# Internet-Weitergabe für alles, was am Access Point hängt. Sie muss
# also in beiden Betriebsarten laufen - ein erneutes "up" auf einer
# bereits aktiven Bridge würde die Verbindungen der angemeldeten
# Geräte unnötig unterbrechen, deshalb vorher nachsehen.
#
bridge_sicherstellen() {

    if ! nmcli -t -f NAME connection show --active | grep -qx "XRack-Bridge"; then
        nmcli -w 10 connection up "XRack-Bridge" >/dev/null 2>&1 || true
    fi
}

if [ "${MODE}" = "on" ]; then

    #
    # Exklusiv zur Ethernet+Heimnetz-Freigabe - beide wollen eth0 für
    # sich.
    #
    nmcli connection down "XRack-Share-eth0" >/dev/null 2>&1 || true
    nmcli connection modify "XRack-Share-eth0" connection.autoconnect no 2>/dev/null || true

    #
    # Ein anderes, mitgeliefertes eth0-Profil ("Wired connection 1")
    # würde sich das Interface beim nächsten Start zurückholen.
    #
    ETH0_CON="$(nmcli -t -f NAME,DEVICE connection show | awk -F: '$2=="eth0"{print $1; exit}')"

    if [ -n "${ETH0_CON}" ] && [ "${ETH0_CON}" != "XRack-Bridge-eth0" ]; then
        nmcli connection modify "${ETH0_CON}" connection.autoconnect no
    fi

    bridge_sicherstellen

    nmcli connection modify "XRack-Bridge-eth0" connection.autoconnect yes
    nmcli connection up "XRack-Bridge-eth0" ifname eth0

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

    nmcli connection down "XRack-Bridge-eth0" >/dev/null 2>&1 || true
    nmcli connection modify "XRack-Bridge-eth0" connection.autoconnect no

    #
    # Die Bridge bleibt bewusst oben - der Access Point funkt weiter
    # hinein.
    #
    bridge_sicherstellen

else
    echo "Unbekannter Modus: ${MODE} (erwartet: on oder off)" >&2
    exit 1
fi
