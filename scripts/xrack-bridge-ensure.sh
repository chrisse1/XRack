#!/usr/bin/env bash
#
# Stellt sicher, dass die Bridge br0 läuft UND ihre Adresse trägt.
#
# Warum die zweite Bedingung: "Verbindung aktiv" und "Bridge trägt
# ihre IP" sind nicht dasselbe. Im Betrieb wurde folgendes beobachtet
# (Protokoll vom 26.08.):
#
#   23:27:43  attached bridge port eth0 ... Activation: successful
#   23:27:46  carrier: link connected
#   (danach kein einziges DHCP-Paket mehr)
#
# Das angeschlossene Pult hat also gefragt - es hatte eine Lease aus
# dem anderen Netz und musste fragen - aber niemand hat geantwortet.
# In der Gegenrichtung kam zwei Sekunden nach demselben Ablauf ein
# DHCPACK. Der Unterschied lag damit nicht am Umschalten, sondern an
# der antwortenden Seite: Auf br0 hat kein DHCP-Server geantwortet.
#
# Die Vermutung dazu (nicht bewiesen): Beim Umschalten auf die
# Heimnetz-Freigabe verliert br0 seinen einzigen von NetworkManager
# verwalteten Anschluss - der Access Point gehört ja hostapd und ist
# für NetworkManager unsichtbar. Räumt NetworkManager daraufhin die
# IP-Konfiguration ab, ist mit ihr auch der DHCP-Server weg, und er
# kommt nicht von selbst zurück.
#
# Dieses Skript ist deshalb kein Beweis und keine Ursachenbehebung,
# sondern ein Netz: Fehlt die Adresse, wird die Bridge neu
# hochgefahren. Ist alles in Ordnung - der Normalfall - passiert
# nichts. Das ist wichtig, denn ein Neuaufbau unterbricht kurz den
# IP-Verkehr der am Access Point angemeldeten Geräte.
#
# Wird von den Umschalt-Skripten aufgerufen, die bereits als root
# laufen - deshalb kein eigener sudo-Eintrag nötig.
#

set -e

BRIDGE="XRack-Bridge"
DEVICE="br0"

neu_aufbauen() {
    nmcli -w 10 connection up "${BRIDGE}" >/dev/null 2>&1 || true
}

#
# Gar nicht aktiv: dann hochfahren, fertig.
#
if ! nmcli -t -f NAME connection show --active | grep -qx "${BRIDGE}"; then
    neu_aufbauen
    exit 0
fi

#
# Aktiv, aber ohne Adresse - genau der Zustand, um den es hier geht.
# "inet " mit Leerzeichen, damit "inet6" nicht mitzählt.
#
if ! ip -4 addr show "${DEVICE}" 2>/dev/null | grep -q "inet "; then
    echo "Bridge ${DEVICE} lief ohne Adresse - wird neu aufgebaut." >&2
    neu_aufbauen
fi
