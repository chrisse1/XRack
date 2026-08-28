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
# Ist noch gar kein Access Point eingerichtet, wird er hier
# angelegt - dafür gibt es scripts/xrack-ap-setup.sh, dasselbe
# Skript, das auch install.sh benutzt. So lässt sich ein Access Point
# jederzeit nachrüsten, ohne install.sh erneut laufen zu lassen.
#
# Wird ausschließlich per sudo durch XRack selbst aufgerufen (siehe
# core/wlan_control.py), nie interaktiv. $1 = SSID, $2 = Passwort,
# $3 = Funkregion (optional).
#

set -e

SSID="$1"
PASSWORD="$2"
COUNTRY="$3"

#
# --refresh-unit: nur die systemd-Unit auffrischen, sonst nichts.
#
# Durchgereicht an xrack-ap-setup.sh. Der Umweg ueber dieses Skript
# ist Absicht: Es hat in /etc/sudoers.d/xrack einen Eintrag mit
# Platzhalter ("xrack-net-ap.sh *"), xrack-ap-setup.sh dagegen nicht.
# XRack kann die Auffrischung damit auch auf einer bestehenden
# Installation anstossen, ohne dass install.sh erneut laufen muss.
#
# Steht vor den Pruefungen auf SSID und Passwort: Fuer das
# Auffrischen gibt es beides nicht, und die Pruefung wuerde hier
# sonst abbrechen.
#
if [ "${SSID}" = "--refresh-unit" ]; then
    exec "$(dirname "$0")/xrack-ap-setup.sh" --refresh-unit
fi

#
# --report: Die Teile der Access-Point-Konfiguration ausgeben, an die
# XRack selbst nicht herankommt.
#
# /etc/hostapd/xrack.conf enthaelt das WLAN-Passwort im Klartext und
# ist deshalb nur fuer root lesbar (siehe xrack-ap-info.sh). Fuer den
# Selbsttest werden daraus Interface, Band, Kanal und Laendercode
# gebraucht - das Passwort ausdruecklich nicht, deshalb wird hier
# gefiltert statt die Datei durchzureichen.
#
# Wieder ueber dieses Skript und nicht als eigenes: Nur "xrack-net-ap.sh *"
# hat einen sudoers-Eintrag mit Platzhalter. Ein neues Skript braeuchte
# einen neuen Eintrag, und den schreibt nur install.sh - der Selbsttest
# waere auf jeder bestehenden Installation tot, also genau dort, wo man
# ihn braucht.
#
if [ "${SSID}" = "--report" ]; then

    if [ -f "${CONF}" ]; then
        grep -E "^(interface|country_code|hw_mode|channel|ieee80211d|bridge)=" \
            "${CONF}" 2>/dev/null || true
    fi

    if [ -f /etc/systemd/system/xrack-hostapd.service ]; then
        grep -E "^# XRack-Unit-Version:" \
            /etc/systemd/system/xrack-hostapd.service 2>/dev/null || true
    fi

    exit 0
fi

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

#
# Region zuerst - sie entscheidet mit darüber, auf welchem Band der
# Access Point ueberhaupt funken darf.
#
if [ -n "${COUNTRY}" ]; then
    "$(dirname "$0")/xrack-wifi-country.sh" "${COUNTRY}" || true
fi

#
# Geraetenamen abgleichen, bevor irgendetwas geschrieben wird: Steht
# in der hostapd-Konfiguration ein Name, der inzwischen dem
# eingebauten WLAN gehoert, wuerde der Access Point auf dem falschen
# Chip landen (siehe xrack-wifi-bind.sh).
#
"$(dirname "$0")/xrack-wifi-bind.sh" || true

# ------------------------------------------------------------------
# Weg 0: Es gibt noch gar keinen Access Point
#
# Genau der Nachruestfall: Bei der Installation wurde "kein Access
# Point" gewaehlt (oder es steckte noch kein USB-WLAN-Stick), und
# jetzt soll doch einer her. Dann wird er hier komplett eingerichtet -
# ohne dass install.sh noch einmal laufen muss.
# ------------------------------------------------------------------

if [ ! -f "${CONF}" ] \
   && ! nmcli -t -f NAME connection show 2>/dev/null | grep -qx "XRack-AP"; then

    SETUP="$(dirname "$0")/xrack-ap-setup.sh"

    if [ ! -x "${SETUP}" ]; then
        echo "Einrichtungsskript fehlt: ${SETUP}" >&2
        exit 1
    fi

    #
    # Die Funkregion wird mitgegeben, statt sie in ap-setup aus
    # "iw reg get" zu lesen: Ist noch gar keine gesetzt, liefert das
    # dort die Weltregion 00 - und die laesst hostapd nicht auf 5 GHz.
    # Der Access Point saesse dann still auf 2,4 GHz fest.
    #
    exec "${SETUP}" "${SSID}" "${PASSWORD}" "${COUNTRY}"
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
