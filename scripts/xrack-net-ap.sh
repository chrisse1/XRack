#!/usr/bin/env bash
#
# Setzt SSID und Passwort des Access Points neu und startet ihn neu.
#
# Der Access Point läuft normalerweise über hostapd (siehe den
# Kommentarblock zum Access Point in install.sh). Auf Geräten, auf
# denen hostapd bei der Installation nicht startete, ist stattdessen
# der alte Weg über NetworkManager eingerichtet - deshalb kann dieses
# Skript beides. Welcher Weg gilt, entscheidet allein, ob es die
# hostapd-Konfiguration gibt.
#
# Wird ausschließlich per sudo durch XRack selbst aufgerufen (siehe
# core/wlan_control.py), nie interaktiv. $1 = SSID, $2 = Passwort.
#

set -e

SSID="$1"
PASSWORD="$2"

CONF="/etc/hostapd/xrack.conf"
UNIT="xrack-hostapd.service"

if [ -z "${SSID}" ] || [ "${#PASSWORD}" -lt 8 ]; then
    echo "SSID fehlt oder Passwort zu kurz (mind. 8 Zeichen)." >&2
    exit 1
fi

#
# Zeilenumbrüche würden in der hostapd-Konfiguration eine neue
# Einstellung erzeugen - der Rest der Zeile landete dann als Befehl
# in der Datei. Deshalb hier abweisen statt später zu rätseln.
#
case "${SSID}${PASSWORD}" in
    *[$'\n\r']*)
        echo "SSID oder Passwort enthält einen Zeilenumbruch." >&2
        exit 1
        ;;
esac

if [ "${#SSID}" -gt 32 ]; then
    echo "SSID ist zu lang (höchstens 32 Zeichen)." >&2
    exit 1
fi

if [ "${#PASSWORD}" -gt 63 ]; then
    echo "Passwort ist zu lang (höchstens 63 Zeichen)." >&2
    exit 1
fi

# ------------------------------------------------------------------
# Weg 1: hostapd
# ------------------------------------------------------------------

if [ -f "${CONF}" ]; then

    #
    # Erst eine Sicherung anlegen: Kommt der Access Point mit den
    # neuen Werten nicht hoch, ist es allemal besser, wieder mit den
    # alten zu funken, als gar nicht. Sonst stünde jemand nach einem
    # Tippfehler ohne Zugang zum Gerät da - und der Zugang ist bei
    # einem Access Point nicht selten der einzige.
    #
    BACKUP="$(mktemp)"
    cp "${CONF}" "${BACKUP}"

    NEU="$(mktemp)"

    #
    # Nur die beiden Zeilen ersetzen, alles andere unverändert
    # übernehmen (Band, Kanal, Verschlüsselung, Ländercode).
    #
    awk -v ssid="${SSID}" -v psk="${PASSWORD}" '
        /^ssid=/          { print "ssid=" ssid;          gefunden_ssid = 1; next }
        /^wpa_passphrase=/ { print "wpa_passphrase=" psk; gefunden_psk = 1;  next }
                          { print }
        END {
            if (!gefunden_ssid) print "ssid=" ssid
            if (!gefunden_psk)  print "wpa_passphrase=" psk
        }
    ' "${BACKUP}" > "${NEU}"

    install -o root -g root -m 0600 "${NEU}" "${CONF}"
    rm -f "${NEU}"

    #
    # Ein Fehlschlag darf hier nicht durch "set -e" das Skript
    # beenden - sonst bliebe die neue, offenbar untaugliche
    # Konfiguration stehen und der Rückfall weiter unten liefe nie.
    #
    systemctl restart "${UNIT}" >/dev/null 2>&1 || true

    #
    # hostapd braucht einen Moment, bis es funkt oder aufgibt.
    #
    sleep 3

    if ! systemctl is-active --quiet "${UNIT}"; then

        install -o root -g root -m 0600 "${BACKUP}" "${CONF}"
        rm -f "${BACKUP}"

        systemctl restart "${UNIT}" || true

        echo "Access Point kam mit den neuen Werten nicht hoch - alte Einstellungen wiederhergestellt." >&2
        exit 1
    fi

    rm -f "${BACKUP}"
    exit 0
fi

# ------------------------------------------------------------------
# Weg 2: NetworkManager (Rückfall, siehe oben)
# ------------------------------------------------------------------

if ! nmcli -t -f NAME connection show | grep -qx "XRack-AP"; then
    echo "Es ist kein Access Point eingerichtet (install.sh mit WLAN-Setup ausführen)." >&2
    exit 1
fi

IFACE="$(nmcli -g connection.interface-name connection show "XRack-AP")"

nmcli connection modify "XRack-AP" \
    802-11-wireless.ssid "${SSID}" \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.proto rsn \
    wifi-sec.psk "${PASSWORD}" \
    wifi-sec.psk-flags 0 \
    connection.autoconnect yes

# Läuft der Access Point bereits, übernimmt ein reines "connection
# up" auf der schon aktiven Verbindung SSID/Passwort-Änderungen
# nicht zuverlässig live (der Funkbetrieb läuft mit den alten Werten
# weiter, das Profil zeigt aber schon die neuen - "falsches
# Passwort" trotz korrektem, gespeichertem Passwort). Deshalb hier
# ausdrücklich erst herunter-, dann wieder hochfahren.
nmcli connection down "XRack-AP" >/dev/null 2>&1 || true

nmcli connection up "XRack-AP" ifname "${IFACE}"
