#!/usr/bin/env bash
#
# Bringt die Funkgeraete-Namen wieder mit ihren Rollen in Deckung.
#
# Warum das noetig ist: wlan0 und wlan1 werden in der Reihenfolge
# vergeben, in der die Geraete auftauchen - nicht fest je Geraet. Beim
# Booten kann deshalb der USB-Stick wlan0 werden und das eingebaute
# WLAN wlan1, statt umgekehrt. Im Feld ist genau das beobachtet
# worden.
#
# An drei Stellen stand bis Version 1.7.2 ein Name fest, der dabei
# falsch wird:
#
#   1. /etc/hostapd/xrack.conf, Zeile "interface=" - hostapd wuerde
#      den Access Point auf dem eingebauten Chip aufzuspannen
#      versuchen (kein 5 GHz, bricht unter Last ein).
#   2. Die NetworkManager-Datei, die das AP-Geraet unverwaltet setzt -
#      sie wuerde dem eingebauten WLAN die Verwaltung entziehen, und
#      dann kommt die Heimnetz-Verbindung nicht mehr hoch.
#   3. Das Profil "XRack-Home" mit connection.interface-name - es
#      zeigte auf den Stick statt auf den eingebauten Chip.
#
# Welches Geraet welche Rolle hat, sagt xrack-wifi-iface.sh - und das
# entscheidet nach USB ja/nein, nicht nach Namen. Das ist die
# verlaessliche Quelle, gegen die hier abgeglichen wird.
#
# Aufgerufen wird das Skript aus xrack-hostapd.service (ExecStartPre,
# deckt jeden Bootvorgang ab) sowie aus xrack-net-ap.sh und
# xrack-net-home.sh. Es laeuft dort jeweils schon als root und hat
# deshalb - wie xrack-wifi-country.sh - keinen eigenen
# sudoers-Eintrag.
#
# Endet immer mit 0: Ein Fehlschlag hier darf hostapd nicht am
# Starten hindern.
#

CONF="${XRACK_HOSTAPD_CONF:-/etc/hostapd/xrack.conf}"
NM_UNMANAGED="${XRACK_NM_UNMANAGED:-/etc/NetworkManager/conf.d/99-xrack-hostapd.conf}"
SYS_NET="${XRACK_SYS_NET:-/sys/class/net}"

IFACE_SKRIPT="$(dirname "$0")/xrack-wifi-iface.sh"

CLIENT="$(XRACK_SYS_NET="${SYS_NET}" "${IFACE_SKRIPT}" client 2>/dev/null || true)"
AP="$(XRACK_SYS_NET="${SYS_NET}" "${IFACE_SKRIPT}" ap 2>/dev/null || true)"

geaendert_nm=0

# ------------------------------------------------------------------
# 1. hostapd: interface= auf das tatsaechliche AP-Geraet
# ------------------------------------------------------------------

if [ -n "${AP}" ] && [ -f "${CONF}" ]; then

    ALT="$(awk -F= '/^interface=/ { print $2; exit }' "${CONF}")"

    if [ "${ALT}" != "${AP}" ]; then

        echo "XRack: AP-Gerät heißt jetzt '${AP}' (vorher '${ALT}')." >&2

        NEU="$(mktemp)"

        awk -v iface="${AP}" '
            /^interface=/ { print "interface=" iface; gefunden = 1; next }
                          { print }
            END { if (!gefunden) print "interface=" iface }
        ' "${CONF}" > "${NEU}"

        install -o root -g root -m 0600 "${NEU}" "${CONF}" || true
        rm -f "${NEU}"
    fi
fi

# ------------------------------------------------------------------
# 2. NetworkManager: das AP-Geraet ueber seine MAC unverwaltet setzen
#
# Ueber die MAC statt ueber den Namen - dann ist dieser Eintrag gegen
# das Umbenennen von vornherein unempfindlich, und es bleibt bei
# einer Stelle, die nachgezogen werden muss (der hostapd-Zeile oben,
# denn hostapd kennt nur Namen).
# ------------------------------------------------------------------

if [ -n "${AP}" ]; then

    MAC="$(cat "${SYS_NET}/${AP}/address" 2>/dev/null || true)"

    if [ -n "${MAC}" ]; then

        GEWUENSCHT="unmanaged-devices=mac:${MAC}"

        if ! grep -qxF "${GEWUENSCHT}" "${NM_UNMANAGED}" 2>/dev/null; then

            mkdir -p "$(dirname "${NM_UNMANAGED}")"

            NEU="$(mktemp)"

            {
                echo "# Von XRack erzeugt (scripts/xrack-wifi-bind.sh) - nicht von"
                echo "# Hand aendern. Das Access-Point-Geraet gehoert hostapd, nicht"
                echo "# NetworkManager. IP, DHCP und NAT macht NetworkManager"
                echo "# weiterhin - aber auf der Bridge br0."
                echo "#"
                echo "# Angesprochen ueber die MAC-Adresse, weil wlan0/wlan1 beim"
                echo "# Booten die Plaetze tauschen koennen."
                echo "[keyfile]"
                echo "${GEWUENSCHT}"
            } > "${NEU}"

            install -o root -g root -m 0644 "${NEU}" "${NM_UNMANAGED}" || true
            rm -f "${NEU}"

            geaendert_nm=1
        fi
    fi
fi

# ------------------------------------------------------------------
# 3. Das Heimnetz-Profil auf das eingebaute WLAN
# ------------------------------------------------------------------

if [ -n "${CLIENT}" ] \
   && nmcli -t -f NAME connection show 2>/dev/null | grep -qx "XRack-Home"; then

    ALT="$(nmcli -g connection.interface-name connection show "XRack-Home" 2>/dev/null || true)"

    if [ "${ALT}" != "${CLIENT}" ]; then

        echo "XRack: Heimnetz-Gerät heißt jetzt '${CLIENT}' (vorher '${ALT}')." >&2

        nmcli connection modify "XRack-Home" \
            connection.interface-name "${CLIENT}" >/dev/null 2>&1 || true
    fi
fi

# ------------------------------------------------------------------
# 4. NetworkManager die geaenderte Konfiguration lesen lassen
# ------------------------------------------------------------------

if [ "${geaendert_nm}" -eq 1 ]; then
    nmcli general reload conf >/dev/null 2>&1 || true
fi

if [ -n "${AP}" ]; then
    nmcli device set "${AP}" managed no >/dev/null 2>&1 || true
fi

exit 0
