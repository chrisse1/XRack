#!/usr/bin/env bash
#
# Setzt die WLAN-Funkregion (Ländercode nach ISO 3166, zwei
# Buchstaben).
#
# Warum das eine eigene Einstellung braucht: Ohne gesetzte Region
# bleibt das Funkgerät auf Raspberry Pi OS per rfkill gesperrt, und
# hostapd darf auf 5 GHz überhaupt nicht senden - der Access Point
# landet dann still auf 2,4 GHz. Bis Version 1.7.1 wurde die Region
# nur von install.sh gefragt, und auch nur dann, wenn man dort WLAN
# oder einen Access Point eingerichtet hat. Wer beides übersprungen
# hat, konnte anschließend zwar beides nachrüsten - aber ohne Region,
# und damit im besseren Fall halb und im schlechteren gar nicht.
#
# Dieses Skript wird NICHT selbst per sudo aufgerufen. Es hat deshalb
# auch keinen eigenen Eintrag in /etc/sudoers.d/xrack. Aufgerufen wird
# es aus xrack-net-home.sh und xrack-net-ap.sh heraus, die per sudo
# bereits als root laufen. Das ist Absicht: Ein neuer sudoers-Eintrag
# entsteht nur, wenn install.sh erneut läuft - und das Update sagt
# zwar Bescheid, führt es aber nicht aus. Die Einstellung wäre auf
# jeder bestehenden Installation tot gewesen.
#
# $1 = Ländercode (zwei Buchstaben, Groß-/Kleinschreibung egal)
#

set -e

CODE="$(printf '%s' "$1" | tr '[:lower:]' '[:upper:]')"

if ! printf '%s' "${CODE}" | grep -qE '^[A-Z]{2}$'; then
    echo "Ungültiger Ländercode: '${1}' (erwartet werden zwei Buchstaben)." >&2
    exit 1
fi

#
# raspi-config ist der vorgesehene Weg auf dem Pi: Es schreibt die
# Region so, dass sie einen Neustart übersteht, und hebt die
# rfkill-Sperre gleich mit auf. Fehlt es (kein Raspberry Pi OS), bleibt
# der Weg von Hand.
#
if command -v raspi-config >/dev/null 2>&1; then
    raspi-config nonint do_wifi_country "${CODE}"
else
    rfkill unblock wifi || true
    iw reg set "${CODE}" || true
fi

#
# Läuft bereits ein Access Point, hat seine Konfiguration die alte
# Region (oder gar keine). Ohne diesen Schritt bliebe das Umstellen
# folgenlos: Der Access Point würde weiter auf 2,4 GHz funken, und
# niemand käme darauf, warum - die Einstellung sagt ja, es sei alles
# gesetzt.
#
CONF="/etc/hostapd/xrack.conf"

if [ -f "${CONF}" ]; then

    NEU="$(mktemp)"

    #
    # country_code und ieee80211d ersetzen, sonst alles unverändert
    # übernehmen. Fehlten die Zeilen (Access Point ohne Region
    # eingerichtet), kommen sie ans Ende - hostapd ist die Reihenfolge
    # gleich.
    #
    awk -v code="${CODE}" '
        /^country_code=/ { print "country_code=" code; gefunden = 1; next }
        /^ieee80211d=/   { next }
                         { print }
        END {
            if (!gefunden) print "country_code=" code
            print "ieee80211d=1"
        }
    ' "${CONF}" > "${NEU}"

    install -o root -g root -m 0600 "${NEU}" "${CONF}"
    rm -f "${NEU}"

    #
    # Ein Fehlschlag darf hier nicht das ganze Skript beenden: Die
    # Region ist dann bereits gesetzt, und das ist der eigentliche
    # Zweck. Dass der Access Point nicht neu startet, ist ein eigenes
    # Problem und keines, das die Region rückgängig machen sollte.
    #
    systemctl restart xrack-hostapd.service >/dev/null 2>&1 || true
fi
