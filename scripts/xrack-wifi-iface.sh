#!/usr/bin/env bash
#
# Sagt, welches Funkgerät wofür zuständig ist.
#
#   $1 = "client"  -> das Interface für die Verbindung ins Heimnetz
#   $1 = "ap"      -> das Interface für den eigenen Access Point
#
# Gibt den Namen aus oder nichts, wenn es kein passendes gibt.
#
# Die Regel dahinter, und warum sie nicht abgefragt wird:
#
# Das eingebaute WLAN des Raspberry Pi taugt als Client, aber nur
# schlecht als Access Point - der Chip kann zwar AP-Betrieb, bricht
# unter Last aber gern ein und beherrscht kein 5 GHz. Ein
# USB-WLAN-Stick ist umgekehrt genau dafür da. Damit ist die
# Zuordnung immer dieselbe: eingebaut = Client, USB = Access Point.
# Eine Abfrage danach hat nur Gelegenheit gegeben, es falsch
# einzustellen.
#
# Erkannt wird über /sys statt über NetworkManager, weil das
# AP-Interface diesem ja gerade entzogen wird (siehe
# xrack-ap-setup.sh) - es taucht dort dann nicht mehr wie erwartet
# auf.
#

set -e

ROLLE="$1"

#
# Wo der Kernel seine Netzwerkgeraete auflistet. Ueberschreibbar,
# damit der Test einen nachgestellten Baum unterschieben kann - so
# laesst sich die Zuordnung ohne echte Funkgeraete pruefen.
#
SYS_NET="${XRACK_SYS_NET:-/sys/class/net}"

#
# Alle Funkgeräte: Ein Netzwerkgerät ist genau dann WLAN, wenn es
# unter /sys ein "wireless"-Verzeichnis hat.
#
funkgeraete() {
    local pfad geraet
    for pfad in "${SYS_NET}"/*/wireless; do
        [ -e "${pfad}" ] || continue
        geraet="$(basename "$(dirname "${pfad}")")"
        echo "${geraet}"
    done
}

#
# Hängt das Gerät am USB? Der Verweis unter "device" zeigt bei einem
# Stick in den USB-Zweig des Geräte-Baums.
#
haengt_am_usb() {
    local ziel
    ziel="$(readlink -f "${SYS_NET}/$1/device" 2>/dev/null || true)"
    case "${ziel}" in
        *"/usb"*) return 0 ;;
        *) return 1 ;;
    esac
}

INTERN=""
EXTERN=""

while read -r geraet; do

    [ -n "${geraet}" ] || continue

    if haengt_am_usb "${geraet}"; then
        [ -n "${EXTERN}" ] || EXTERN="${geraet}"
    else
        [ -n "${INTERN}" ] || INTERN="${geraet}"
    fi

done < <(funkgeraete)

case "${ROLLE}" in

    client)
        #
        # Ohne eingebautes WLAN muss der Stick herhalten - dann gibt
        # es eben keinen Access Point.
        #
        echo "${INTERN:-${EXTERN}}"
        ;;

    ap)
        #
        # Nur wenn es ein zweites Funkgerät gibt. Das eingebaute
        # allein bleibt dem Heimnetz vorbehalten.
        #
        if [ -n "${EXTERN}" ]; then
            echo "${EXTERN}"
        fi
        ;;

    *)
        echo "Unbekannte Rolle: ${ROLLE} (erwartet: client oder ap)" >&2
        exit 1
        ;;
esac
