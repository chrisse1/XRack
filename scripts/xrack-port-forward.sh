#!/usr/bin/env bash
#
# Macht die per Ethernet+AP-Bridge oder Ethernet+Heimnetz-Freigabe
# angeschlossene Konsole aus dem Heimnetz heraus erreichbar - die
# Konsole steckt sonst in einem eigenen, von XRack per NAT
# abgeschotteten Netz (siehe core/wlan_control.py: get_status()),
# das vom Heimnetz aus nicht direkt ansprechbar ist.
#
# Statt echtem Routing (setzt eine vom Heimrouter unterstützte
# statische Route voraus, die die meisten einfachen Router-
# Weboberflächen nicht anbieten) leitet dieses Skript per DNAT genau
# die beiden UDP-Ports weiter, die die gängigen Steuerungs-Apps
# nutzen:
#   - 10023: X32-Edit / X32 (X32/M32-Serie)
#   - 10024: X-AIR-Edit / Mixing Station (XR12/16/18)
# Von der Steuerungs-App aus zeigt man dafür also auf die IP von
# XRack selbst im Heimnetz (Port 10023/10024), nicht auf die
# Konsolen-IP.
#
# Nutzt eine eigene iptables-Chain (statt einzelner Regeln), damit
# "on" bei geänderter Konsolen-IP einfach die Chain leert und neu
# aufbaut, ohne die alte IP kennen zu müssen. Keine Einschränkung auf
# ein bestimmtes Quell-Interface - die Konsole ist über ihre eigene
# (bereits NAT-geschützte) Adresse ohnehin nur über XRack erreichbar,
# das schränkt das Risiko einer offenen Weiterleitung ausreichend ein.
#
# Wird ausschließlich per sudo durch XRack selbst aufgerufen (siehe
# core/wlan_control.py), nie interaktiv.
#   $1 = "on" (mit $2 = Konsolen-IP) oder "off"
#

set -e

MODE="$1"

CHAIN_NAT="XRACK-PORTFWD"
CHAIN_FWD="XRACK-PORTFWD-FWD"

PORTS="10023 10024"

ensure_chains() {

    iptables -t nat -N "${CHAIN_NAT}" 2>/dev/null || true
    iptables -t nat -C PREROUTING -j "${CHAIN_NAT}" 2>/dev/null \
        || iptables -t nat -A PREROUTING -j "${CHAIN_NAT}"

    iptables -N "${CHAIN_FWD}" 2>/dev/null || true
    iptables -C FORWARD -j "${CHAIN_FWD}" 2>/dev/null \
        || iptables -A FORWARD -j "${CHAIN_FWD}"
}

if [ "${MODE}" = "on" ]; then

    CONSOLE_IP="$2"

    if [ -z "${CONSOLE_IP}" ]; then
        echo "Keine Konsolen-IP angegeben." >&2
        exit 1
    fi

    ensure_chains

    iptables -t nat -F "${CHAIN_NAT}"
    iptables -F "${CHAIN_FWD}"

    for PORT in ${PORTS}; do
        iptables -t nat -A "${CHAIN_NAT}" -p udp --dport "${PORT}" \
            -j DNAT --to-destination "${CONSOLE_IP}:${PORT}"
        iptables -A "${CHAIN_FWD}" -p udp -d "${CONSOLE_IP}" --dport "${PORT}" \
            -j ACCEPT
    done

elif [ "${MODE}" = "off" ]; then

    ensure_chains

    iptables -t nat -F "${CHAIN_NAT}"
    iptables -F "${CHAIN_FWD}"

else
    echo "Unbekannter Modus: ${MODE} (erwartet: on <ip> oder off)" >&2
    exit 1
fi
