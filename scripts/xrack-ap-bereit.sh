#!/usr/bin/env bash
#
# Ist das Funkgeraet fuer den Access Point ueberhaupt da?
#
#   Rueckgabe 0 = ja, hostapd kann starten
#   Rueckgabe 1 = nein, es gibt nichts aufzuspannen
#
# Gedacht als ExecCondition in xrack-hostapd.service. Der Unterschied
# zu ExecStartPre ist genau der Punkt: Eine gescheiterte Bedingung
# laesst systemd den Dienst UEBERSPRINGEN - ohne Fehlschlag, ohne dass
# die uebrigen Exec-Zeilen laufen.
#
# Der Anlass steht in einem Journal vom Geraet. Der AP war
# eingerichtet, der USB-Stick aber nicht eingesteckt, weil er in
# diesem Szenario nicht gebraucht wurde. Damit lief Folgendes, alle
# fuenf Sekunden, einundzwanzig Stunden lang:
#
#   xrack-hostapd.service: Scheduled restart job, restart counter
#   is at 14453.
#   nmcli connection up XRack-Bridge   (ExecStartPre)
#   hostapd: Main process exited, code=exited, status=1/FAILURE
#
# Der Fehlstart allein waere Laerm im Journal. Schlimmer ist die
# Zeile davor: Jeder Versuch liess NetworkManager die Bruecke neu
# aktivieren - alle fuenf Sekunden ein Eingriff ins Netz, rund um die
# Uhr. Genau daneben standen im Protokoll die Netzaussetzer, hinter
# denen wir tagelang her waren.
#
# Mit der Bedingung davor wird aus dem schaedlichen Hammern ein
# einziger, stiller Verzicht: Steckt der Stick nicht, ueberspringt
# systemd den Dienst und versucht es NICHT wieder - ein
# uebersprungener Start wird auch bei Restart=always nicht
# wiederholt.
#
# Das ist genau der Grund, warum es zusaetzlich die udev-Regel
# 99-xrack-ap.rules gibt (geschrieben von xrack-ap-setup.sh): Das
# Hammern hatte die angenehme Nebenwirkung, den spaeter
# eingesteckten Stick zu bemerken. Diese Faehigkeit haette die
# Bedingung sonst mitgenommen.
#

set -e

IFACE_SKRIPT="$(dirname "$0")/xrack-wifi-iface.sh"

AP="$("${IFACE_SKRIPT}" ap 2>/dev/null || true)"

if [ -z "${AP}" ]; then
    echo "XRack: Kein Funkgerät für den Access Point vorhanden." >&2
    exit 1
fi

exit 0
