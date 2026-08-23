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
# WICHTIGER FUND (per Live-Diagnose bestätigt): NetworkManager legt
# für "ipv4.method shared" (das benutzen sowohl die Ethernet+AP-
# Bridge als auch die Ethernet+Heimnetz-Freigabe) automatisch eine
# EIGENE nftables-Tabelle an ("nm-shared-eth0" bzw. "nm-shared-br0"),
# deren Firewall-Kette per Default JEDE neue, von außen initiierte
# Verbindung zum geteilten Subnetz ablehnt (nur bereits bestehende
# Verbindungen dürfen durch). Diese Tabelle wird UNABHÄNGIG von
# unserer eigenen ausgewertet - ein "accept" in unserer eigenen Kette
# verhindert nicht, dass NetworkManagers eigene Kette dasselbe Paket
# trotzdem ablehnt (mehrere an denselben Netfilter-Hook angehängte
# Ketten werden unabhängig voneinander durchlaufen, DROP/REJECT in
# irgendeiner davon beendet die Verarbeitung sofort). Die einzige
# zuverlässige Lösung: eine explizite Ausnahme an den ANFANG von
# NetworkManagers eigener Kette einfügen, vor deren pauschalen
# reject-Regeln - das übernimmt dieses Skript zusätzlich zu DNAT.
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

#
# NetworkManagers Tabelle heißt "nm-shared-<interface>" - je nachdem,
# ob gerade die Ethernet+Heimnetz-Freigabe (eth0) oder die
# Ethernet+AP-Bridge (br0) aktiv ist, existiert nur eine der beiden.
#
detect_nm_shared_table() {

    if nft list table ip nm-shared-eth0 >/dev/null 2>&1; then
        echo "nm-shared-eth0"
    elif nft list table ip nm-shared-br0 >/dev/null 2>&1; then
        echo "nm-shared-br0"
    fi
}

ensure_chains() {

    #
    # Sprung in die eigene Chain jeweils an Position 1 einfügen (nicht
    # anhängen) - unabhängig von der NetworkManager-Ausnahme unten,
    # damit auch diese Kette so früh wie möglich zum Zug kommt.
    #

    iptables -t nat -N "${CHAIN_NAT}" 2>/dev/null || true
    iptables -t nat -C PREROUTING -j "${CHAIN_NAT}" 2>/dev/null \
        || iptables -t nat -I PREROUTING 1 -j "${CHAIN_NAT}"

    iptables -N "${CHAIN_FWD}" 2>/dev/null || true
    iptables -C FORWARD -j "${CHAIN_FWD}" 2>/dev/null \
        || iptables -I FORWARD 1 -j "${CHAIN_FWD}"
}

#
# Entfernt zuvor von uns in NetworkManagers eigene Kette eingefügte
# Ausnahme-Regeln (an unserem Kommentar "xrack-portfwd" erkennbar) -
# egal ob das gerade die eth0- oder die br0-Tabelle ist, damit beim
# Wechsel zwischen Bridge und Freigabe keine Leiche zurückbleibt.
#
remove_nm_exceptions() {

    for TABLE in nm-shared-eth0 nm-shared-br0; do

        if ! nft list chain ip "${TABLE}" filter_forward >/dev/null 2>&1; then
            continue
        fi

        nft -a list chain ip "${TABLE}" filter_forward 2>/dev/null \
            | grep 'comment "xrack-portfwd"' \
            | grep -oP 'handle \K[0-9]+' \
            | while read -r RULE_HANDLE; do
                nft delete rule ip "${TABLE}" filter_forward handle "${RULE_HANDLE}" 2>/dev/null || true
            done
    done
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

    #
    # Ohne diese Regel würde nur die Anfrage zur Konsole durchgelassen,
    # nicht aber deren Antwort zurück zum anfragenden Gerät.
    #
    iptables -A "${CHAIN_FWD}" -s "${CONSOLE_IP}" \
        -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

    #
    # Die eigentlich entscheidende Ausnahme (siehe Kommentar oben) -
    # direkt an den Anfang von NetworkManagers eigener Kette.
    #
    remove_nm_exceptions

    NM_TABLE="$(detect_nm_shared_table)"

    if [ -n "${NM_TABLE}" ]; then
        for PORT in ${PORTS}; do
            nft insert rule ip "${NM_TABLE}" filter_forward \
                ip daddr "${CONSOLE_IP}" udp dport "${PORT}" accept comment "xrack-portfwd"
        done
    else
        echo "Warnung: NetworkManagers Freigabe-/Bridge-Firewall wurde nicht gefunden - ist Bridge oder Freigabe aktiv?" >&2
    fi

elif [ "${MODE}" = "off" ]; then

    ensure_chains

    iptables -t nat -F "${CHAIN_NAT}"
    iptables -F "${CHAIN_FWD}"

    remove_nm_exceptions

else
    echo "Unbekannter Modus: ${MODE} (erwartet: on <ip> oder off)" >&2
    exit 1
fi
