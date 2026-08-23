#!/usr/bin/env bash
#
# Liest die DHCP-Lease-Datei aus, die NetworkManagers eingebauter
# dnsmasq bei "ipv4.method shared" für ein Interface führt (z.B.
# Ethernet+AP-Bridge oder Ethernet+Heimnetz-Freigabe) - zeigt so die
# IP des per Kabel angeschlossenen Mischpults im Einstellungen-Modal
# an, ohne auf tatsächlichen IP-Verkehr nach der Lease-Vergabe
# angewiesen zu sein (siehe core/wlan_control.py:
# get_connected_client_ip() für den ARP-basierten Fallback, falls
# diese Datei nicht existiert/lesbar ist).
#
# Wird ausschließlich per sudo durch XRack selbst aufgerufen (siehe
# core/wlan_control.py), nie interaktiv. $1 = Interface-Name (z.B.
# br0 oder eth0). Gibt bei Erfolg genau eine Zeile mit der zuletzt
# vergebenen IP aus, sonst nichts (kein Fehler - eine fehlende/leere
# Lease-Datei ist der Normalfall, solange nichts angeschlossen ist).
#

set -e

IFACE="$1"

LEASE_FILE="/var/lib/NetworkManager/dnsmasq-${IFACE}.leases"

if [ ! -r "${LEASE_FILE}" ]; then
    exit 0
fi

#
# Format je Zeile: "<ablauf-timestamp> <mac> <ip> <hostname> <client-id>".
# Nur die zuletzt vergebene (letzte Zeile) Lease ausgeben, falls doch
# mehrere Geräte je an diesem Interface hingen.
#
tail -n 1 "${LEASE_FILE}" 2>/dev/null | awk '{print $3}'
