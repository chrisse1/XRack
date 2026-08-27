#!/usr/bin/env bash
#
# Bringt die Netzwerkbuchse zurück in den Normalbetrieb: ein ganz
# gewöhnlicher DHCP-Client, so wie an jedem Router.
#
# Das ist Betriebsart 1 aus dem Installer - XRack und Mischpult hängen
# zusammen an einem Router - und zugleich der Ruhezustand, wenn weder
# die Bridge noch die Heimnetz-Freigabe eingeschaltet ist.
#
# Warum es das braucht:
#
# NetworkManager erzeugt seine automatische Kabelverbindung nur
# solange, wie für das Gerät gar kein Profil passt. Sobald XRack
# eigene anlegt - die Bridge und die Freigabe, beide bewusst mit
# "autoconnect no" -, hört das auf. Ohne ein drittes Profil mit
# "autoconnect yes" bliebe die Buchse danach ohne aktives Profil
# liegen: keine Adresse, im Router nicht zu sehen, per Kabel nicht
# erreichbar. Genau das ist im Feld passiert.
#
# Wird von den Umschalt-Skripten beim Ausschalten aufgerufen, die
# bereits als root laufen - deshalb kein eigener sudo-Eintrag nötig.
#

set -e

WIRED="XRack-Wired-eth0"

#
# Das Profil gibt es erst seit dieser Fassung. Auf einem Gerät, das
# XRack schon länger hat, wird es hier angelegt - so muss dafür
# niemand install.sh erneut durchlaufen lassen.
#
if ! nmcli -t -f NAME connection show | grep -qx "${WIRED}"; then

    nmcli connection add type ethernet ifname eth0 con-name "${WIRED}" \
        ipv4.method auto connection.autoconnect yes >/dev/null || exit 0
fi

nmcli connection modify "${WIRED}" connection.autoconnect yes 2>/dev/null || true

#
# Läuft schon etwas anderes auf der Buchse (die Bridge oder die
# Freigabe), wird hier nichts hochgefahren - das würde dem gerade
# eingeschalteten Betrieb in die Quere kommen. Das "autoconnect yes"
# oben genügt dann: Beim nächsten Start greift es.
#
BELEGT="$(nmcli -t -f NAME,DEVICE connection show --active | awk -F: '$2=="eth0"{print $1; exit}')"

if [ -n "${BELEGT}" ] && [ "${BELEGT}" != "${WIRED}" ]; then
    exit 0
fi

nmcli connection up "${WIRED}" ifname eth0 >/dev/null 2>&1 || true
