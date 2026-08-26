#!/usr/bin/env bash
#
# Trennt kurz die Verbindung auf einem Netzwerkanschluss und stellt sie
# wieder her - macht also das nach, was ein Ab- und Anstecken des Kabels
# bewirkt.
#
# Wozu das nötig ist:
#
# Die beiden Zugangswege zur Konsole liegen in verschiedenen Netzen -
# die Ethernet+AP-Bridge vergibt 10.42.0.x, die Heimnetz-Freigabe
# 10.77.0.x (siehe install.sh). Beim Umschalten stellt sich der Pi
# sofort um. Das angeschlossene Mischpult tut das aber nicht: Es fragt
# erst dann wieder per DHCP nach einer Adresse, wenn die Verbindung
# tatsächlich weg war. Ein Profilwechsel in NetworkManager lässt die
# Verbindung durchgehend bestehen - das Pult merkt also nichts und
# behält seine alte Adresse, bis die Lease abläuft. Das dauert eine
# Stunde.
#
# Genau deshalb half bisher nur Kabel ziehen oder ein Neustart. Beides
# unterbricht die Verbindung, und danach holt sich das Pult eine
# passende Adresse.
#
# Wird von den Umschalt-Skripten aufgerufen, die bereits als root
# laufen - deshalb kein eigener sudo-Eintrag nötig.
#
# $1 = Anschluss (z.B. eth0)
#

set -e

IFACE="$1"

if [ -z "${IFACE}" ]; then
    echo "Kein Anschluss angegeben." >&2
    exit 1
fi

#
# Anschluss gibt es nicht - dann gibt es auch nichts zu trennen. Kein
# Fehler: Nicht jede Installation hat jeden Anschluss.
#
# Geprüft wird über "ip" statt über /sys, damit derselbe Befehl das
# Vorhandensein feststellt, der gleich darauf schaltet.
#
if ! ip link show "${IFACE}" >/dev/null 2>&1; then
    exit 0
fi

#
# Kurz trennen. "ip" gehört zu iproute2 und ist auf jedem Raspberry Pi
# OS vorhanden - anders als etwa ethtool.
#
ip link set "${IFACE}" down
sleep 1
ip link set "${IFACE}" up

#
# Dem Pult einen Moment geben, die neue Adresse zu holen. Ohne das
# zeigte die Oberfläche direkt nach dem Umschalten noch "keine
# Verbindung", obwohl gleich darauf alles läuft.
#
sleep 2
