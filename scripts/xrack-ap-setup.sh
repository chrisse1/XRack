#!/usr/bin/env bash
#
# Richtet den Access Point ein - Funk, Verschluesselung, Dienst.
#
#   $1 = SSID
#   $2 = Passwort (mind. 8 Zeichen)
#   $3 = Laendercode (optional; leer = aus der Funkregion lesen)
#
# Warum das ein eigenes Skript ist und nicht mehr in install.sh
# steht:
#
# Wer bei der Installation "kein Access Point" waehlt, soll ihn
# spaeter im Einstellungen-Menue nachruesten koennen, ohne install.sh
# noch einmal durchlaufen zu lassen. Dafuer muss die Einrichtung von
# beiden Seiten aufrufbar sein - vom Installer und von XRack selbst
# (ueber scripts/xrack-net-ap.sh, das hierher weiterreicht, wenn es
# noch keine Konfiguration gibt).
#
# Laeuft als root: aus install.sh per sudo, aus XRack heraus ueber
# xrack-net-ap.sh, das selbst schon per sudo laeuft.
#
# Der ausfuehrliche Hintergrund - warum hostapd und nicht
# NetworkManager - steht im Kommentarblock zum Access Point in
# install.sh.
#

set -e

AP_SSID="$1"
AP_PASSWORD="$2"
AP_COUNTRY="$3"

#
# Zwei Betriebsarten:
#
#   (ohne)           Access Point komplett einrichten
#   --refresh-unit   nur die systemd-Unit neu schreiben
#
# Die zweite braucht weder SSID noch Passwort noch einen
# angesteckten Stick - die Konfiguration bleibt ja, wie sie ist.
# Deshalb werden die Vorpruefungen dafuer uebersprungen.
#
NUR_UNIT="nein"

if [ "${1:-}" = "--refresh-unit" ]; then
    NUR_UNIT="ja"
fi


#
# Die Zielpfade. Ueberschreibbar, damit der Test die Einrichtung
# einmal komplett durchspielen kann, ohne am System zu schrauben -
# sonst liesse sich genau der Teil nicht pruefen, den man auf dem
# Geraet am schwersten nachstellt.
#
XRACK_HOSTAPD_CONF="${XRACK_HOSTAPD_CONF:-/etc/hostapd/xrack.conf}"
XRACK_HOSTAPD_UNIT="${XRACK_HOSTAPD_UNIT:-/etc/systemd/system/xrack-hostapd.service}"

#
# Stand der systemd-Unit.
#
# Hochzaehlen, sobald sich am Inhalt der Unit etwas aendert. XRack
# vergleicht diese Zahl beim Start mit der Marke in der installierten
# Unit und laesst sie neu schreiben, wenn sie zurueckliegt (siehe
# core/wlan_control.py).
#
# Warum es das braucht: Die Unit wurde frueher nur beim Anlegen des
# Access Points geschrieben. Ein Update brachte zwar den neuen Text
# mit, fasste die installierte Datei aber nie an - neue
# ExecStartPre-Zeilen erreichten ein laufendes Geraet also nie. Der
# Aufruf im Updater half nicht: xrack-update.py startet sich vor dem
# Kopieren neu, es laeuft also stets die alte Fassung des Updaters.
# Deshalb prueft XRack selbst, nach dem Update, mit dem neuen Code.
#
# 1 = urspruengliche Unit
# 2 = mit ExecStartPre fuer xrack-wifi-bind.sh (Namensabgleich)
#
XRACK_UNIT_VERSION="2"
XRACK_NM_UNMANAGED="${XRACK_NM_UNMANAGED:-/etc/NetworkManager/conf.d/99-xrack-hostapd.conf}"

#
# Der Abgleich der Geraetenamen, den die Unit vor jedem Start
# aufruft. Absoluter Pfad, weil systemd kein Arbeitsverzeichnis
# mitbringt.
#
XRACK_BIND_SKRIPT="$(cd "$(dirname "$0")" && pwd)/xrack-wifi-bind.sh"

if [ "${NUR_UNIT}" = "nein" ]; then

    if [ -z "${AP_SSID}" ] || [ "${#AP_PASSWORD}" -lt 8 ]; then
        echo "SSID fehlt oder Passwort zu kurz (mind. 8 Zeichen)." >&2
        exit 1
    fi

    #
    # Zeilenumbrueche wuerden in der hostapd-Konfiguration eine neue
    # Einstellung erzeugen - der Rest der Zeile landete dann als Befehl
    # in der Datei.
    #
    case "${AP_SSID}${AP_PASSWORD}" in
        *[$'\n\r']*)
            echo "SSID oder Passwort enthaelt einen Zeilenumbruch." >&2
            exit 1
            ;;
    esac

    if [ "${#AP_SSID}" -gt 32 ] || [ "${#AP_PASSWORD}" -gt 63 ]; then
        echo "SSID (max. 32) oder Passwort (max. 63) ist zu lang." >&2
        exit 1
    fi

    #
    # Welches Funkgeraet? Immer das per USB angeschlossene - siehe
    # xrack-wifi-iface.sh.
    #
    AP_IFACE="$("$(dirname "$0")/xrack-wifi-iface.sh" ap)"

    if [ -z "${AP_IFACE}" ]; then
        echo "Kein zweites WLAN-Geraet gefunden - fuer einen Access Point wird ein USB-WLAN-Stick gebraucht." >&2
        exit 1
    fi

    #
    # Ohne Laenderangabe darf hostapd auf 5 GHz gar nicht senden. Wurde
    # keine mitgegeben, die gerade geltende lesen.
    #
    if [ -z "${AP_COUNTRY}" ]; then
        AP_COUNTRY="$(iw reg get 2>/dev/null | awk '/^country/ {print $2}' | tr -d ':' | head -n 1)"
    fi

fi


#
# hostapd-Konfiguration schreiben.
#
# $1 = Interface, $2 = SSID, $3 = Passwort, $4 = Laendercode (darf
# leer sein), $5 = hw_mode (a/g), $6 = Kanal
#
write_hostapd_conf() {

    HOSTAPD_TMP="$(mktemp)"

    {
        echo "# Von XRack erzeugt (scripts/xrack-ap-setup.sh) - nicht von Hand"
        echo "# aendern. SSID und Passwort werden ueber das"
        echo "# Einstellungen-Menue gesetzt (scripts/xrack-net-ap.sh)."
        echo "interface=$1"
        echo "bridge=br0"
        echo "driver=nl80211"
        echo "ssid=$2"

        #
        # Ohne Laendercode duerfte hostapd auf 5 GHz gar nicht senden.
        # "00" ist die Welt-Region und erlaubt dort ebenfalls nichts -
        # dann bleibt es bei 2,4 GHz ohne Laenderangabe.
        #
        if [ -n "$4" ] && [ "$4" != "00" ]; then
            echo "country_code=$4"
            echo "ieee80211d=1"
        fi

        echo "hw_mode=$5"
        echo "channel=$6"
        echo "ieee80211n=1"
        echo "wmm_enabled=1"
        echo "auth_algs=1"
        echo "macaddr_acl=0"
        echo "ignore_broadcast_ssid=0"

        #
        # WPA2 mit AES (CCMP), ausdruecklich ohne das alte TKIP: Neuere
        # Handys handeln TKIP mitunter aus und scheitern dann am
        # Schluesselaustausch.
        #
        echo "wpa=2"
        echo "wpa_key_mgmt=WPA-PSK"
        echo "rsn_pairwise=CCMP"

        #
        # Geschuetzte Verwaltungsrahmen angeboten, aber nicht
        # verlangt (1 = optional): Schutz gegen Abmelde-Angriffe fuer
        # alles, was es kann, ohne aeltere Geraete auszusperren.
        #
        echo "ieee80211w=1"

        echo "wpa_passphrase=$3"

    } > "${HOSTAPD_TMP}"

    install -o root -g root -m 0600 "${HOSTAPD_TMP}" "${XRACK_HOSTAPD_CONF}"

    rm -f "${HOSTAPD_TMP}"
}


#
# Den Dienst anlegen und starten; liefert 0, wenn der Access Point
# danach tatsaechlich funkt.
#
# $1 = Interface
#
start_xrack_hostapd() {

    systemctl restart xrack-hostapd.service >/dev/null 2>&1 || true

    #
    # hostapd braucht einen Moment, bis das Interface im AP-Betrieb
    # ist. Ein sofortiges Nachsehen meldete sonst Fehlschlag, obwohl
    # gleich darauf alles laeuft.
    #
    sleep 4

    if ! systemctl is-active --quiet xrack-hostapd.service; then
        return 1
    fi

    #
    # Zusaetzlich am Interface selbst nachsehen: Der Dienst kann
    # laufen und hostapd trotzdem im Leerlauf haengen (z.B. weil die
    # Funkregion den Kanal nicht freigibt).
    #
    if ! iw dev "$1" info 2>/dev/null | grep -q "type AP"; then
        return 1
    fi

    return 0
}


#
# Access Point mit hostapd einrichten.
#
# $1 = Interface, $2 = SSID, $3 = Passwort, $4 = Laendercode
#
# Liefert 0 bei Erfolg. Bei Fehlschlag wird das Interface wieder an
# NetworkManager zurueckgegeben, damit der Rueckfallweg greifen kann.
#
#
# Die systemd-Unit schreiben.
#
# Eigene Funktion, weil sie an zwei Stellen gebraucht wird: beim
# Einrichten des Access Points und beim Nachziehen nach einem Update
# (--refresh-unit). Ohne das zweite bekaeme eine bestehende
# Installation neue ExecStartPre-Zeilen nie zu sehen - die Unit wird
# sonst nur beim Anlegen geschrieben.
#
write_hostapd_unit() {

    tee "${XRACK_HOSTAPD_UNIT}" > /dev/null <<EOF
# XRack-Unit-Version: ${XRACK_UNIT_VERSION}
[Unit]
Description=XRack Access Point (hostapd)
After=NetworkManager.service
Wants=NetworkManager.service

[Service]
Type=simple
# Ein per rfkill gesperrtes Funkgeraet ist der haeufigste Grund,
# warum hostapd direkt nach dem Booten nicht startet.
ExecStartPre=-/usr/sbin/rfkill unblock wlan
# wlan0/wlan1 werden nach Reihenfolge vergeben, nicht fest je Geraet -
# beim Booten koennen Stick und eingebautes WLAN die Plaetze tauschen.
# Deshalb vor jedem Start abgleichen, welcher Name gerade zu welcher
# Rolle gehoert (siehe scripts/xrack-wifi-bind.sh).
ExecStartPre=-${XRACK_BIND_SKRIPT}
# Die Bridge muss es geben, bevor hostapd sich hineinhaengt. Kurzer
# Zeitrahmen, damit ein fehlendes Kabel den Start nicht aufhaelt;
# ein Fehlschlag ist unschaedlich (hostapd legt br0 sonst selbst an).
ExecStartPre=-/usr/bin/nmcli -w 5 connection up XRack-Bridge
ExecStart=/usr/sbin/hostapd ${XRACK_HOSTAPD_CONF}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl disable hostapd.service >/dev/null 2>&1 || true
    systemctl enable xrack-hostapd.service >/dev/null 2>&1 || true
}

#
# --refresh-unit: Nur die systemd-Unit neu schreiben, sonst nichts
# anfassen.
#
# Gebraucht nach einem Update. Die Unit wird sonst ausschliesslich
# beim Anlegen des Access Points geschrieben - eine bestehende
# Installation bekaeme neue ExecStartPre-Zeilen also nie zu sehen,
# und der Abgleich der Geraetenamen liefe dort nie an. Aufgerufen
# wird das von scripts/xrack-update.py.
#
# Steht hinter write_hostapd_unit und den Pfad-Variablen, weil Bash
# das Skript von oben nach unten liest - weiter oben waere die
# Funktion noch nicht bekannt.
#
if [ "${1:-}" = "--refresh-unit" ]; then

    if [ ! -f "${XRACK_HOSTAPD_CONF}" ]; then
        # Kein Access Point eingerichtet - dann gibt es nichts zu tun.
        exit 0
    fi

    write_hostapd_unit
    exit 0
fi

setup_access_point_hostapd() {

    AP_HW_MODE="g"
    AP_CHANNEL="6"

    #
    # 5 GHz bevorzugen, wenn der Adapter und die Funkregion es
    # hergeben: 2,4 GHz ist in Wohngegenden meist zugestellt, und ein
    # volles Band erzeugt dasselbe Bild wie eine falsche
    # Verschluesselung - die Anmeldung geht im Stoernebel unter.
    #
    # Geprueft wird an Kanal 36 (5180 MHz), weil der weltweit
    # ueblichste 5-GHz-Kanal ohne Radarpflicht ist. Ein Kanal zaehlt
    # nur, wenn er weder "disabled" noch "no IR" ist - "no IR"
    # heisst, dass dort nicht von sich aus gesendet werden darf, ein
    # Access Point also gerade nicht erlaubt ist.
    #
    if [ -n "$4" ] && [ "$4" != "00" ]; then

        AP_PHY="$(iw dev "$1" info 2>/dev/null | awk '/wiphy/ {print $2}')"

        if [ -n "${AP_PHY}" ]; then

            #
            # Die Frequenz steht je nach iw-Version als "5180 MHz"
            # oder als "5180.0 MHz" in der Ausgabe - deshalb sind die
            # Nachkommastellen hier ausdruecklich erlaubt. Ein
            # Muster nur fuer die ganzzahlige Schreibweise fand auf
            # neueren Systemen nie etwas und liess den Access Point
            # stillschweigend auf 2,4 GHz.
            #
            AP_CHAN36="$(iw phy "phy${AP_PHY}" info 2>/dev/null \
                | grep -E '\* 5180(\.[0-9]+)? MHz' | head -n 1)"

            if [ -n "${AP_CHAN36}" ] \
               && ! printf '%s' "${AP_CHAN36}" | grep -qE 'disabled|no IR'; then

                AP_HW_MODE="a"
                AP_CHANNEL="36"
            fi
        fi
    fi

    write_hostapd_conf "$1" "$2" "$3" "$4" "${AP_HW_MODE}" "${AP_CHANNEL}"

    #
    # Das Interface NetworkManager entziehen. Ohne das wuerde NM sein
    # wpa_supplicant weiter darauf loslassen - zwei Programme auf
    # einem Funkgeraet.
    #
    mkdir -p "$(dirname "${XRACK_NM_UNMANAGED}")"

    tee "${XRACK_NM_UNMANAGED}" > /dev/null <<EOF
# Von install.sh erzeugt (XRack): Das Access-Point-Interface gehoert
# hostapd (siehe /etc/systemd/system/xrack-hostapd.service), nicht
# NetworkManager. IP, DHCP und NAT macht NetworkManager weiterhin -
# aber auf der Bridge br0, in der hostapd den Access Point einhaengt.
[keyfile]
unmanaged-devices=interface-name:$1
EOF

    write_hostapd_unit

    nmcli device set "$1" managed no >/dev/null 2>&1 || true
    systemctl reload NetworkManager >/dev/null 2>&1 || true

    nmcli -w 10 connection up "XRack-Bridge" >/dev/null 2>&1 || true

    if start_xrack_hostapd "$1"; then
        return 0
    fi

    #
    # Auf 5 GHz nicht hochgekommen - dann zurueck auf 2,4 GHz, statt
    # den Nutzer ohne Access Point dastehen zu lassen.
    #
    if [ "${AP_HW_MODE}" = "a" ]; then

        echo "5 GHz hat nicht funktioniert - Access Point wird auf 2,4 GHz gestellt." >&2

        AP_HW_MODE="g"
        AP_CHANNEL="6"

        write_hostapd_conf "$1" "$2" "$3" "$4" "${AP_HW_MODE}" "${AP_CHANNEL}"

        if start_xrack_hostapd "$1"; then
            return 0
        fi
    fi

    #
    # hostapd laeuft ueberhaupt nicht. Interface zurueck an
    # NetworkManager geben, damit der Rueckfallweg (der alte
    # NM-Hotspot) es wieder benutzen darf.
    #
    systemctl disable --now xrack-hostapd.service >/dev/null 2>&1 || true
    rm -f "${XRACK_NM_UNMANAGED}"
    systemctl reload NetworkManager >/dev/null 2>&1 || true
    nmcli device set "$1" managed yes >/dev/null 2>&1 || true

    return 1
}


#
# Rueckfallweg: der alte Access Point ueber NetworkManager.
#
# Bleibt erhalten, damit auf einem Geraet, auf dem hostapd nicht
# startet (fehlendes Paket, Treiber ohne AP-Unterstuetzung), nicht
# gar kein Access Point herauskommt. Er wird genauso in die Bridge
# eingehaengt wie der hostapd-Weg - dadurch bleiben die
# Umschalt-Skripte fuer beide Faelle dieselben.
#
# $1 = Interface, $2 = SSID, $3 = Passwort
#
setup_access_point_nm() {

    nmcli connection delete "XRack-AP" >/dev/null 2>&1 || true

    nmcli connection add type wifi ifname "$1" con-name "XRack-AP" \
        ssid "$2" mode ap >/dev/null || return 1

    nmcli connection modify "XRack-AP" \
        master "XRack-Bridge" slave-type bridge \
        wifi-sec.key-mgmt wpa-psk \
        wifi-sec.proto rsn \
        wifi-sec.pairwise ccmp \
        wifi-sec.group ccmp \
        wifi-sec.psk "$3" \
        wifi-sec.psk-flags 0 \
        connection.autoconnect yes || return 1

    nmcli connection up "XRack-Bridge" >/dev/null 2>&1 || true

    nmcli connection up "XRack-AP" ifname "$1" >/dev/null 2>&1 || return 1

    return 0
}

if setup_access_point_hostapd "${AP_IFACE}" "${AP_SSID}" "${AP_PASSWORD}" "${AP_COUNTRY}"; then

    #
    # Ein noch vorhandenes altes Hotspot-Profil aus NetworkManager
    # entfernen: Es funkt zwar nicht mehr (das Interface gehoert
    # jetzt hostapd), wuerde aber in der Oberflaeche und in den
    # Umschalt-Skripten weiter als Access Point gelten.
    #
    nmcli connection delete "XRack-AP" >/dev/null 2>&1 || true

    if [ "${AP_HW_MODE}" = "a" ]; then
        echo "Access Point laeuft auf 5 GHz (hostapd)."
    else
        echo "Access Point laeuft auf 2,4 GHz (hostapd)."
    fi

    exit 0
fi

echo "hostapd liess sich nicht starten - es wird der bisherige Weg ueber NetworkManager versucht." >&2

if setup_access_point_nm "${AP_IFACE}" "${AP_SSID}" "${AP_PASSWORD}"; then
    echo "Access Point laeuft ueber NetworkManager."
    exit 0
fi

echo "Access Point konnte nicht eingerichtet werden." >&2
exit 1
