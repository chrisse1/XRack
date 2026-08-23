#!/usr/bin/env bash
#
# XRack Setup-Skript für Raspberry Pi OS / Debian.
#
# Installiert alle System- und Python-Abhängigkeiten und legt eine
# virtuelle Python-Umgebung (.venv) an.
#
# Aufbau: Jeder Installationsschritt ist eine eigene Funktion. Der
# eigentliche Ablauf steht ganz am Ende der Datei (Abschnitt "Ablauf").
# Ab der Sprachwahl (choose_language) laufen alle weiteren Meldungen
# über den Helper L() in der gewählten Sprache (Deutsch/Englisch).
#

set -e

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

#
# Der eigentliche Zielbenutzer für Dienst und Dateibesitz (systemd
# "User=", USB-Automount-UID/GID, sudoers-Regel). Läuft install.sh wie
# vorgesehen als normaler Benutzer (./install.sh, mit sudo nur für
# einzelne Befehle), liefert whoami/id den richtigen Nutzer. Wurde es
# stattdessen versehentlich komplett per "sudo ./install.sh" gestartet,
# liefern whoami/id sonst "root" statt des echten Pi-Nutzers - SUDO_USER
# ist in dem Fall aber gesetzt und wird deshalb bevorzugt ausgewertet.
#
XRACK_TARGET_USER="${SUDO_USER:-$(whoami)}"

lower() {
    printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

#
# Gibt je nach gewählter Sprache (XRACK_LANGUAGE) den deutschen oder
# englischen Text zurück - Aufruf: "$(L "Deutscher Text" "English text")".
# Vor der Sprachwahl (choose_language) ist XRACK_LANGUAGE leer, dann
# liefert L() immer den deutschen Text.
#
L() {
    if [ "${XRACK_LANGUAGE}" = "en" ]; then
        printf '%s' "$2"
    else
        printf '%s' "$1"
    fi
}

#
# Prüft, ob eine Ja/Nein-Antwort eine Zustimmung ist - deutsch "j",
# englisch "y" (je nach XRACK_LANGUAGE), unabhängig von Groß-/
# Kleinschreibung.
#
confirm_yes() {
    local answer
    answer="$(lower "$1")"

    if [ "${XRACK_LANGUAGE}" = "en" ]; then
        [ "${answer}" = "y" ]
    else
        [ "${answer}" = "j" ]
    fi
}

#
# Begrüßung + Bestätigung, bevor irgendetwas am System verändert
# wird. Läuft vor der Sprachwahl, deshalb fest auf Englisch. Nur bei
# interaktivem Lauf - per "curl | bash" geht es stillschweigend weiter.
#
confirm_start() {

    if [ -t 0 ]; then

        echo "XRack Setup"
        echo ""
        echo "This installer will install XRack on this system"
        echo "(system packages, Python environment, systemd service)."
        echo ""
        read -r -p "Continue? [Y/n]: " XRACK_CONFIRM_START || true

        if [ "$(lower "${XRACK_CONFIRM_START}")" = "n" ]; then
            echo "Aborted - nothing was changed."
            exit 0
        fi
    fi
}

#
# Sprache wählen - passiert ganz am Anfang (vor allen anderen
# Schritten), damit alle nachfolgenden Meldungen (Abhängigkeiten,
# WLAN, Bluetooth, Zusammenfassung, ...) in der gewählten Sprache
# erscheinen. Läuft das Skript nicht interaktiv, bleibt es bei
# Deutsch als Standard.
#
choose_language() {

    XRACK_LANGUAGE="de"

    if [ -t 0 ]; then

        echo ""
        read -r -p "Sprache / Language [de/en] (Standard/default: de): " XRACK_LANGUAGE_INPUT || true

        if [ "$(lower "${XRACK_LANGUAGE_INPUT}")" = "en" ]; then
            XRACK_LANGUAGE="en"
        fi
    fi
}

#
# Fragt ein Passwort/eine PIN doppelt ab und wiederholt die Eingabe
# bei Tippfehlern (falsche Wiederholung, zu kurz oder falsches
# Format), statt stillschweigend weiterzulaufen und den betroffenen
# Schritt später unbemerkt zu überspringen. Leer/leer gilt als
# bewusstes Überspringen. Nach 3 Fehlversuchen wird abgebrochen.
#
read_confirmed_secret() {
    local prompt="$1"
    local min_length="$2"
    local -n out_var="$3"
    local pattern="${4:-}"
    local repeat_label
    local value
    local confirm
    local attempt

    repeat_label="$(L "Wiederholung" "repeat")"

    for attempt in 1 2 3; do

        read -r -s -p "${prompt}: " value || true
        echo ""
        read -r -s -p "${prompt} (${repeat_label}): " confirm || true
        echo ""

        # Leer/leer = bewusst übersprungen (z.B. dieses optionale
        # WLAN-Profil oder die PIN nicht einrichten) - kein Fehlversuch.
        if [ -z "${value}" ] && [ -z "${confirm}" ]; then
            out_var=""
            return 0
        fi

        if [ "${value}" != "${confirm}" ]; then
            echo "$(L "Die beiden Eingaben stimmen nicht überein - bitte erneut eingeben." "The two entries don't match - please try again.")"
            continue
        fi

        if [ "${#value}" -lt "${min_length}" ]; then
            echo "$(L "Eingabe zu kurz (mind. ${min_length} Zeichen) - bitte erneut eingeben." "Input too short (min. ${min_length} characters) - please try again.")"
            continue
        fi

        if [ -n "${pattern}" ] && ! [[ "${value}" =~ ${pattern} ]]; then
            echo "$(L "Ungültiges Format - bitte erneut eingeben." "Invalid format - please try again.")"
            continue
        fi

        out_var="${value}"
        return 0
    done

    echo "$(L "Zu viele Fehlversuche - dieser Schritt wird übersprungen." "Too many failed attempts - this step will be skipped.")"
    out_var=""
    return 1
}

valid_wifi_index() {
    local index="$1"
    local max="$2"
    [[ "${index}" =~ ^[0-9]+$ ]] && [ "${index}" -ge 1 ] && [ "${index}" -le "${max}" ]
}

#
# System- und Python-Abhängigkeiten installieren, virtuelle
# Python-Umgebung (.venv) anlegen.
#
install_system_dependencies() {

    echo "$(L "XRack: Systemabhängigkeiten werden installiert (ohne Ausgabe, kann etwas dauern)..." "XRack: Installing system dependencies (no output, this may take a while)...")"

    sudo apt-get update -qq

    sudo apt-get install -y -qq \
        python3 \
        python3-venv \
        python3-pip \
        libasound2-dev \
        alsa-utils \
        ffmpeg \
        bluez \
        bluez-alsa-utils \
        python3-dbus \
        python3-gi \
        openssl \
        exfatprogs \
        ntfs-3g \
        iptables > /dev/null

    echo "$(L "XRack: Python-Umgebung wird eingerichtet..." "XRack: Setting up Python environment...")"

    python3 -m venv .venv

    source .venv/bin/activate

    pip install --upgrade pip -q

    pip install -r requirements.txt -q

    deactivate
}

#
# Port, Hostname und PIN abfragen und nach config/local.yaml
# schreiben (die Sprache wurde bereits von choose_language() gesetzt).
#
# Läuft das Skript nicht interaktiv (z.B. per "curl | bash"), werden
# stillschweigend die Standardwerte (Port 8080, Hostname "xrack",
# kein PIN-Schutz) verwendet.
#
configure_basic_settings() {

    XRACK_PORT="8080"
    XRACK_HOSTNAME="xrack"
    XRACK_PIN=""

    if [ -t 0 ]; then

        echo ""
        read -r -p "$(L "Port fürs Webinterface (Standard: 8080): " "Port for the web interface (default: 8080): ")" XRACK_PORT_INPUT || true

        if [ -n "${XRACK_PORT_INPUT}" ] && [ "${XRACK_PORT_INPUT}" -eq "${XRACK_PORT_INPUT}" ] 2>/dev/null; then
            XRACK_PORT="${XRACK_PORT_INPUT}"
        fi

        echo ""
        read -r -p "$(L "Hostname (Standard: xrack, erreichbar als https://<hostname>.local): " "Hostname (default: xrack, reachable as https://<hostname>.local): ")" XRACK_HOSTNAME_INPUT || true

        if [ -n "${XRACK_HOSTNAME_INPUT}" ]; then
            if [[ "${XRACK_HOSTNAME_INPUT}" =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$ ]]; then
                XRACK_HOSTNAME="${XRACK_HOSTNAME_INPUT}"
            else
                echo "$(L "Ungültiger Hostname (nur Buchstaben, Ziffern, Bindestriche) - verwende 'xrack'." "Invalid hostname (letters, digits, hyphens only) - using 'xrack'.")"
            fi
        fi

        echo ""
        echo "$(L "Eine 4-stellige PIN schützt das Einstellungen-Menü (Zahnrad-Symbol) vor unbefugtem Zugriff, z.B. durch Bandmitglieder oder Gäste. Sie lässt sich später jederzeit im Einstellungen-Menü selbst ändern." "A 4-digit PIN protects the settings menu (gear icon) from unauthorized access, e.g. by band members or guests. You can change it any time later in the settings menu itself.")"
        read_confirmed_secret "$(L "PIN fürs Einstellungen-Menü (4 Ziffern, leer = kein Schutz)" "PIN for the settings menu (4 digits, empty = no protection)")" 4 XRACK_PIN "^[0-9]{4}$"

        if [ -z "${XRACK_PIN}" ]; then
            echo "$(L "Kein PIN-Schutz eingerichtet - die Einstellungen sind ungeschützt (später im Einstellungen-Menü nachholbar)." "No PIN protection set up - the settings are unprotected (can be added later in the settings menu).")"
        fi

    fi

    XRACK_PIN_HASH=""

    if [ -n "${XRACK_PIN}" ]; then
        XRACK_PIN_HASH="$(XRACK_PIN="${XRACK_PIN}" python3 -c "
import os
import sys

sys.path.insert(0, '.')

from core.pin import hash_pin

print(hash_pin(os.environ['XRACK_PIN']))
")"
    fi

    echo "$(L "XRack: Konfiguration wird geschrieben (Sprache: ${XRACK_LANGUAGE}, Port: ${XRACK_PORT})..." "XRack: Writing configuration (language: ${XRACK_LANGUAGE}, port: ${XRACK_PORT})...")"

    cat > config/local.yaml <<EOF
application:
  language: "${XRACK_LANGUAGE}"

server:
  port: ${XRACK_PORT}

security:
  pin_hash: "${XRACK_PIN_HASH}"
EOF
}

#
# Hostname setzen, damit der Pi im lokalen Netz per mDNS (Avahi)
# unter https://<hostname>.local erreichbar ist. Avahi kündigt den
# aktuellen System-Hostnamen automatisch an - hier wird nur der
# Hostname gesetzt und Avahi neu gestartet, damit er den neuen Namen
# sofort übernimmt (ohne Reboot).
#
configure_hostname_and_avahi() {

    echo "$(L "XRack: Hostname wird gesetzt (${XRACK_HOSTNAME})..." "XRack: Setting hostname (${XRACK_HOSTNAME})...")"

    sudo hostnamectl set-hostname "${XRACK_HOSTNAME}"

    if grep -q "^127.0.1.1" /etc/hosts; then
        sudo sed -i "s/^127.0.1.1.*/127.0.1.1\t${XRACK_HOSTNAME}/" /etc/hosts
    else
        echo -e "127.0.1.1\t${XRACK_HOSTNAME}" | sudo tee -a /etc/hosts > /dev/null
    fi

    if command -v avahi-daemon >/dev/null 2>&1; then
        sudo systemctl enable avahi-daemon >/dev/null 2>&1 || true
        sudo systemctl restart avahi-daemon
    else
        echo "$(L "Hinweis: avahi-daemon nicht gefunden - '${XRACK_HOSTNAME}.local' wird im Netzwerk nicht auffindbar sein." "Note: avahi-daemon not found - '${XRACK_HOSTNAME}.local' won't be discoverable on the network.")"
    fi
}

#
# Selbstsigniertes TLS-Zertifikat erzeugen, damit das Webinterface
# über HTTPS läuft. Ein "echtes", von Browsern automatisch akzeptiertes
# Zertifikat (Let's Encrypt) funktioniert hier nicht - dafür bräuchte
# es eine öffentliche, per DNS auflösbare Domain, XRack läuft aber oft
# komplett offline über einen eigenen Access Point. Browser zeigen beim
# ersten Aufruf deshalb einmalig eine Sicherheitswarnung
# ("Verbindung ist nicht privat" o.ä.) - "Erweitert" -> "Trotzdem
# fortfahren" reicht, danach merkt sich der Browser die Ausnahme für
# dieses Gerät. Zehn Jahre Gültigkeit, damit das nicht regelmäßig
# erneut bestätigt werden muss. Wird bei jedem install.sh-Lauf neu
# erzeugt (falls sich der Hostname geändert hat), eine bereits erteilte
# Browser-Ausnahme muss dann einmalig erneut bestätigt werden.
#
generate_tls_certificate() {

    echo "$(L "XRack: Selbstsigniertes TLS-Zertifikat wird erzeugt..." "XRack: Generating self-signed TLS certificate...")"

    mkdir -p "${INSTALL_DIR}/certs"

    openssl req -x509 -nodes -newkey rsa:2048 \
        -keyout "${INSTALL_DIR}/certs/xrack.key" \
        -out "${INSTALL_DIR}/certs/xrack.crt" \
        -days 3650 \
        -subj "/CN=${XRACK_HOSTNAME}" \
        -addext "subjectAltName=DNS:${XRACK_HOSTNAME},DNS:${XRACK_HOSTNAME}.local,DNS:localhost,IP:127.0.0.1" \
        >/dev/null 2>&1

    chmod 600 "${INSTALL_DIR}/certs/xrack.key"
}

#
# Falls eine Firewall (ufw) aktiv ist, Freigaben für mDNS und das
# Webinterface ergänzen. Auf einem frischen Raspberry Pi OS/Debian
# ist standardmäßig keine Firewall aktiv - dieser Schritt greift nur,
# falls der Nutzer selbst ufw eingerichtet hat.
#
configure_firewall() {

    if command -v ufw >/dev/null 2>&1 && sudo ufw status | grep -q "^Status: active"; then
        echo "$(L "XRack: ufw ist aktiv - Firewall-Regeln werden ergänzt..." "XRack: ufw is active - adding firewall rules...")"
        sudo ufw allow 5353/udp comment 'XRack mDNS (Avahi)'
        sudo ufw allow "${XRACK_PORT}/tcp" comment 'XRack Webinterface'
    fi
}

#
# Optional: WLAN einrichten (Heimnetz-Client + eigener Access Point).
#
# Für Setups mit zwei WLAN-Interfaces, z.B. Onboard-WLAN als Client
# im Heimnetz (Fernzugriff auf XRack) und ein zusätzlicher USB-WLAN-
# Stick als eigener Access Point, über den z.B. eine Misch-App direkt
# mit dem Pi/Mischpult spricht - ganz ohne Router vor Ort. Komplett
# optional und nur bei interaktivem Lauf, per NetworkManager (nmcli).
#
configure_wifi() {

    XRACK_WLAN_CLIENT_SSID=""
    XRACK_WLAN_AP_SSID=""
    XRACK_WLAN_BRIDGE=""
    XRACK_WLAN_SHARE_READY=""

    if [ -t 0 ] && command -v nmcli >/dev/null 2>&1; then

        echo ""
        read -r -p "$(L "WLAN einrichten - Heimnetz-Verbindung + eigener Access Point? [j/N]: " "Set up Wi-Fi - home network connection + your own access point? [y/N]: ")" XRACK_WLAN_SETUP || true

        if confirm_yes "${XRACK_WLAN_SETUP}"; then

            #
            # WLAN-Land setzen. Ohne gesetztes Regulierungsgebiet bleibt
            # WLAN auf frisch aufgesetzten Raspberry Pis oft per rfkill
            # soft-blockiert (Geräte existieren, sind aber "nicht
            # verfügbar") - das kostet sonst viel Fehlersuche. Ungültige
            # Eingaben werden bis zu 3x erneut abgefragt, leer gilt als
            # bewusstes Überspringen.
            #

            XRACK_WLAN_COUNTRY=""

            for attempt in 1 2 3; do

                echo ""
                read -r -p "$(L "WLAN-Land (2-stelliger ISO-Code, z.B. DE/AT/CH/US/GB, leer = überspringen) - nötig, damit WLAN nicht per rfkill blockiert bleibt: " "Wi-Fi country (2-letter ISO code, e.g. DE/AT/CH/US/GB, empty = skip) - needed so Wi-Fi doesn't stay blocked by rfkill: ")" XRACK_WLAN_COUNTRY_INPUT || true

                if [ -z "${XRACK_WLAN_COUNTRY_INPUT}" ]; then
                    break
                fi

                XRACK_WLAN_COUNTRY="$(printf '%s' "${XRACK_WLAN_COUNTRY_INPUT}" | tr '[:lower:]' '[:upper:]')"

                if [[ "${XRACK_WLAN_COUNTRY}" =~ ^[A-Z]{2}$ ]]; then
                    break
                fi

                echo "$(L "Ungültiger Ländercode (genau 2 Buchstaben) - bitte erneut eingeben." "Invalid country code (exactly 2 letters) - please try again.")"
                XRACK_WLAN_COUNTRY=""
            done

            if [ -n "${XRACK_WLAN_COUNTRY}" ]; then

                echo "$(L "XRack: WLAN-Land wird gesetzt (${XRACK_WLAN_COUNTRY})..." "XRack: Setting Wi-Fi country (${XRACK_WLAN_COUNTRY})...")"

                if command -v raspi-config >/dev/null 2>&1; then
                    sudo raspi-config nonint do_wifi_country "${XRACK_WLAN_COUNTRY}"
                else
                    sudo rfkill unblock wifi
                    sudo iw reg set "${XRACK_WLAN_COUNTRY}" || true
                    echo "$(L "Hinweis: raspi-config nicht gefunden - WLAN-Land ist damit ggf. nicht dauerhaft gesetzt (nach einem Neustart mit 'rfkill list' prüfen)." "Note: raspi-config not found - the Wi-Fi country may not be set persistently (check with 'rfkill list' after a reboot).")"
                fi
            else
                echo "$(L "WLAN-Land wird übersprungen (WLAN kann per rfkill blockiert bleiben, siehe 'rfkill list')." "Wi-Fi country setup skipped (Wi-Fi may stay blocked by rfkill, see 'rfkill list').")"
            fi

            mapfile -t WIFI_INTERFACES < <(nmcli -t -f DEVICE,TYPE device status | awk -F: '$2=="wifi"{print $1}')

            if [ "${#WIFI_INTERFACES[@]}" -lt 2 ]; then
                echo "$(L "Es wurden nur ${#WIFI_INTERFACES[@]} WLAN-Interface(s) gefunden - für Client + Access Point werden zwei benötigt. WLAN-Setup übersprungen." "Only ${#WIFI_INTERFACES[@]} Wi-Fi interface(s) found - two are needed for client + access point. Wi-Fi setup skipped.")"
            else

                echo ""
                echo "$(L "Gefundene WLAN-Interfaces:" "Found Wi-Fi interfaces:")"
                for i in "${!WIFI_INTERFACES[@]}"; do
                    echo "  $((i + 1))) ${WIFI_INTERFACES[$i]}"
                done

                CLIENT_IFACE=""
                AP_IFACE=""

                for attempt in 1 2 3; do

                    echo ""
                    read -r -p "$(L "Welches Interface soll sich mit deinem Heimnetz verbinden (Nummer 1-${#WIFI_INTERFACES[@]})? " "Which interface should connect to your home network (number 1-${#WIFI_INTERFACES[@]})? ")" CLIENT_INDEX || true
                    read -r -p "$(L "Welches Interface soll den Access Point aufspannen (Nummer 1-${#WIFI_INTERFACES[@]})? " "Which interface should run the access point (number 1-${#WIFI_INTERFACES[@]})? ")" AP_INDEX || true

                    if valid_wifi_index "${CLIENT_INDEX}" "${#WIFI_INTERFACES[@]}" \
                        && valid_wifi_index "${AP_INDEX}" "${#WIFI_INTERFACES[@]}" \
                        && [ "${CLIENT_INDEX}" != "${AP_INDEX}" ]; then

                        CLIENT_IFACE="${WIFI_INTERFACES[$((CLIENT_INDEX - 1))]}"
                        AP_IFACE="${WIFI_INTERFACES[$((AP_INDEX - 1))]}"
                        break
                    fi

                    echo "$(L "Ungültige oder gleiche Auswahl (gültig: 1-${#WIFI_INTERFACES[@]}, beide unterschiedlich) - bitte erneut eingeben." "Invalid or identical selection (valid: 1-${#WIFI_INTERFACES[@]}, must be different) - please try again.")"
                done

                if [ -z "${CLIENT_IFACE}" ] || [ -z "${AP_IFACE}" ]; then
                    echo "$(L "Zu viele Fehlversuche - WLAN-Setup wird übersprungen." "Too many failed attempts - Wi-Fi setup will be skipped.")"
                else

                    echo ""
                    read -r -p "$(L "Heimnetz-SSID: " "Home network SSID: ")" HOME_SSID || true
                    read_confirmed_secret "$(L "Heimnetz-Passwort (mind. 8 Zeichen)" "Home network password (min. 8 characters)")" 8 HOME_PASSWORD

                    echo ""
                    read -r -p "$(L "Name des Access Points (Standard: XRack): " "Access point name (default: XRack): ")" AP_SSID_INPUT || true
                    AP_SSID="${AP_SSID_INPUT:-XRack}"
                    read_confirmed_secret "$(L "Passwort für den Access Point (mind. 8 Zeichen)" "Access point password (min. 8 characters)")" 8 AP_PASSWORD

                    if [ -z "${HOME_SSID}" ] || [ "${#HOME_PASSWORD}" -lt 8 ]; then
                        echo "$(L "Heimnetz-SSID fehlt oder Passwort fehlt/zu kurz (mind. 8 Zeichen) - Heimnetz-Verbindung übersprungen." "Home network SSID missing, or password missing/too short (min. 8 characters) - home network connection skipped.")"
                    else

                        echo "$(L "XRack: Verbinde ${CLIENT_IFACE} mit '${HOME_SSID}'..." "XRack: Connecting ${CLIENT_IFACE} to '${HOME_SSID}'...")"
                        echo "$(L "Hinweis: Falls du gerade über dieses Interface per WLAN verbunden bist, kann die Verbindung kurz unterbrochen werden." "Note: if you're currently connected over this interface, the connection may briefly drop.")"

                        sudo nmcli connection delete "XRack-Home" >/dev/null 2>&1 || true

                        if sudo nmcli connection add type wifi ifname "${CLIENT_IFACE}" con-name "XRack-Home" \
                            ssid "${HOME_SSID}" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "${HOME_PASSWORD}" \
                            connection.autoconnect yes >/dev/null; then

                            XRACK_WLAN_CLIENT_SSID="${HOME_SSID}"

                            sudo nmcli connection up "XRack-Home" ifname "${CLIENT_IFACE}" \
                                || echo "$(L "Warnung: Verbindung zu '${HOME_SSID}' konnte nicht sofort hergestellt werden (SSID/Passwort prüfen)." "Warning: could not connect to '${HOME_SSID}' immediately (check SSID/password).")"

                            #
                            # Zusätzliche, standardmäßig inaktive Möglichkeit:
                            # Ethernet-Port über die Heimnetz-Verbindung per NAT
                            # freigeben, statt zu bridgen - eine echte Bridge über
                            # eine WLAN-Client-Verbindung funktioniert bei den
                            # meisten Heim-Routern nicht zuverlässig (kein
                            # 4-Adress-WDS), siehe scripts/xrack-share-toggle.sh.
                            # Aktivierung später im Einstellungen-Modal;
                            # schließt sich dort mit der Ethernet+AP-Bridge aus.
                            #

                            sudo nmcli connection delete "XRack-Share-eth0" >/dev/null 2>&1 || true

                            if sudo nmcli connection add type ethernet ifname eth0 con-name "XRack-Share-eth0" \
                                ipv4.method shared connection.autoconnect no >/dev/null; then
                                XRACK_WLAN_SHARE_READY="ja"
                            else
                                echo "$(L "Warnung: Profil für die Ethernet+Heimnetz-Freigabe konnte nicht angelegt werden." "Warning: could not create the Ethernet+home network sharing profile.")"
                            fi
                        else
                            echo "$(L "Warnung: WLAN-Client-Profil konnte nicht angelegt werden." "Warning: could not create the Wi-Fi client profile.")"
                        fi
                    fi

                    if [ "${#AP_PASSWORD}" -lt 8 ]; then
                        echo "$(L "Access-Point-Passwort fehlt/zu kurz (mind. 8 Zeichen) - Access Point übersprungen." "Access point password missing/too short (min. 8 characters) - access point skipped.")"
                    else

                        echo "$(L "XRack: Access Point '${AP_SSID}' wird auf ${AP_IFACE} eingerichtet..." "XRack: Setting up access point '${AP_SSID}' on ${AP_IFACE}...")"

                        sudo nmcli connection delete "XRack-AP" >/dev/null 2>&1 || true

                        if sudo nmcli connection add type wifi ifname "${AP_IFACE}" con-name "XRack-AP" \
                            ssid "${AP_SSID}" mode ap >/dev/null; then

                            sudo nmcli connection modify "XRack-AP" \
                                802-11-wireless.band bg \
                                ipv4.method shared \
                                wifi-sec.key-mgmt wpa-psk \
                                wifi-sec.proto rsn \
                                wifi-sec.psk "${AP_PASSWORD}" \
                                connection.autoconnect yes

                            XRACK_WLAN_AP_SSID="${AP_SSID}"

                            sudo nmcli connection up "XRack-AP" ifname "${AP_IFACE}" \
                                || echo "$(L "Warnung: Access Point konnte nicht gestartet werden." "Warning: the access point could not be started.")"

                            #
                            # Optional: Ethernet-Interface (z.B. das per Kabel
                            # angeschlossene Mischpult) mit dem Access Point
                            # bridgen, damit Steuerungs-Apps (z.B. Mixing
                            # Station) das Pult über den AP finden - beide
                            # landen dann im selben Netz statt in getrennten,
                            # sich gegenseitig nicht sehenden Subnetzen.
                            #

                            echo ""
                            read -r -p "$(L "Ethernet-Interface (z.B. Mischpult an eth0) mit dem Access Point bridgen, damit Apps es finden? [J/n]: " "Bridge an Ethernet interface (e.g. mixing console on eth0) with the access point, so apps can find it? [Y/n]: ")" XRACK_BRIDGE_SETUP || true

                            if [ "$(lower "${XRACK_BRIDGE_SETUP}")" != "n" ]; then

                                echo "$(L "XRack: Bridge aus eth0 und ${AP_IFACE} wird vorbereitet..." "XRack: Preparing a bridge from eth0 and ${AP_IFACE}...")"
                                echo "$(L "Hinweis: Wird jetzt nur angelegt, nicht sofort aktiviert - viele" "Note: this is only set up now, not activated immediately - many")"
                                echo "$(L "konfigurieren den Pi anfangs per SSH über eth0, das würde sonst" "people configure the Pi over SSH via eth0 initially, which would")"
                                echo "$(L "genau jetzt abbrechen. Aktiv wird die Bridge erst nach einem" "otherwise drop right now. The bridge only becomes active after a")"
                                echo "$(L "Neustart (Abfrage dazu kommt ganz am Ende)." "restart (you'll be asked about that at the very end).")"

                                #
                                # Das bisherige eth0-Profil wird nur deaktiviert (nicht
                                # gelöscht!), damit eine gerade laufende SSH-Sitzung
                                # über eth0 nicht sofort abreißt. Es wird erst beim
                                # nächsten Neustart durch das Bridge-Profil ersetzt.
                                #

                                ETH0_CON="$(nmcli -t -f NAME,DEVICE connection show | awk -F: '$2=="eth0"{print $1; exit}')"

                                if [ -n "${ETH0_CON}" ] && [ "${ETH0_CON}" != "XRack-Bridge-eth0" ]; then
                                    sudo nmcli connection modify "${ETH0_CON}" connection.autoconnect no
                                fi

                                sudo nmcli connection delete "XRack-Bridge-eth0" >/dev/null 2>&1 || true
                                sudo nmcli connection delete "XRack-Bridge" >/dev/null 2>&1 || true

                                if sudo nmcli connection add type bridge ifname br0 con-name "XRack-Bridge" \
                                    connection.autoconnect yes >/dev/null \
                                    && sudo nmcli connection modify "XRack-Bridge" ipv4.method shared \
                                    && sudo nmcli connection add type ethernet ifname eth0 con-name "XRack-Bridge-eth0" \
                                        master "XRack-Bridge" slave-type bridge connection.autoconnect yes >/dev/null; then

                                    # Das Setzen von master/slave-type auf dem AP-Profil
                                    # kann dabei das gespeicherte WLAN-Passwort
                                    # zurücksetzen - deshalb wird es im selben Schritt
                                    # gleich wieder mitgesetzt. Die Aktivierung selbst
                                    # (nmcli connection up) passiert bewusst nicht hier,
                                    # sondern erst nach dem Neustart am Ende des Skripts.
                                    sudo nmcli connection modify "XRack-AP" \
                                        master "XRack-Bridge" slave-type bridge \
                                        wifi-sec.psk "${AP_PASSWORD}" \
                                        wifi-sec.psk-flags 0 \
                                        connection.autoconnect yes

                                    XRACK_WLAN_BRIDGE="ja"
                                else
                                    echo "$(L "Warnung: Bridge konnte nicht eingerichtet werden." "Warning: the bridge could not be set up.")"
                                fi
                            fi
                        else
                            echo "$(L "Warnung: Access-Point-Profil konnte nicht angelegt werden." "Warning: could not create the access point profile.")"
                        fi
                    fi

                fi
            fi

        fi

    elif [ -t 0 ]; then
        echo ""
        echo "$(L "Hinweis: nmcli (NetworkManager) nicht gefunden - WLAN-Setup (Heimnetz + Access Point) übersprungen." "Note: nmcli (NetworkManager) not found - Wi-Fi setup (home network + access point) skipped.")"
    fi
}

#
# Bluetooth-Audio einrichten (XRack als Bluetooth-Lautsprecher).
#
# bluez-alsa (bluealsa) registriert ein eigenes A2DP-Sink-Angebot
# beim Bluetooth-Adapter, unabhängig von XRack selbst - der Dienst
# läuft dauerhaft im Hintergrund. Sobald ein Handy/Tablet aktiv Audio
# schickt, liest XRack das über ein ALSA-Capture-Gerät aus (siehe
# player/bluetooth_player.py) und legt es auf das im Webinterface
# gewählte Stereopaar.
#
# Ein separater Kopplungs-Agent (scripts/xrack-bt-agent.py, "Just
# Works", ohne PIN-/Code-Bestätigung) läuft ebenfalls dauerhaft im
# Hintergrund - koppeln kann sich damit trotzdem nur, wer den Adapter
# zuvor per Knopfdruck im Webinterface koppelbar gemacht hat (siehe
# scripts/xrack-bt-pair.sh), ohne das ist der Adapter nicht
# auffindbar. Eigene, minimale Implementierung nach dem offiziellen
# BlueZ-Beispielagenten (statt bt-agent aus bluez-tools, das sich
# gegen aktuelle BlueZ-Versionen als unzuverlässig erwiesen hat).
#
configure_bluetooth() {

    if command -v bluetoothctl >/dev/null 2>&1; then

        echo "$(L "XRack: Bluetooth-Audio (bluealsa) wird eingerichtet..." "XRack: Setting up Bluetooth audio (bluealsa)...")"

        sudo mkdir -p /etc/systemd/system/bluealsa.service.d

        sudo tee /etc/systemd/system/bluealsa.service.d/xrack.conf > /dev/null <<'EOF'
[Service]
ExecStart=
ExecStart=/usr/bin/bluealsa -p a2dp-sink
EOF

        chmod +x "${INSTALL_DIR}/scripts/xrack-bt-agent.py"

        sudo tee /etc/systemd/system/xrack-bt-agent.service > /dev/null <<EOF
[Unit]
Description=XRack Bluetooth-Kopplungs-Agent (Just Works)
After=bluetooth.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 ${INSTALL_DIR}/scripts/xrack-bt-agent.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

        #
        # Das Debian-Paket bluez-alsa-utils bringt einen eigenen Dienst
        # mit (bluealsa-aplay.service, startet "bluealsa-aplay -S" beim
        # Booten), der automatisch JEDEN eingehenden Bluetooth-Audiostream
        # an das System-Standardgerät weiterleitet - ganz ohne Kanalwahl,
        # immer auf Kanal 1+2. Der kollidiert direkt mit XRacks eigener
        # Kanalsteuerung: er schnappt sich die bluealsa-Verbindung zuerst,
        # XRacks eigener Verbindungsversuch scheitert dann mit "Device or
        # resource busy". Muss deaktiviert sein, sonst landet Audio immer
        # auf Kanal 1+2, egal was im Webinterface gewählt wird.
        #

        sudo systemctl disable --now bluealsa-aplay.service >/dev/null 2>&1 || true

        sudo systemctl daemon-reload

        sudo systemctl enable bluetooth.service bluealsa.service xrack-bt-agent.service >/dev/null 2>&1 || true
        sudo systemctl restart bluetooth.service
        sudo systemctl restart bluealsa.service
        sudo systemctl restart xrack-bt-agent.service

    else
        echo ""
        echo "$(L "Hinweis: bluetoothctl (BlueZ) nicht gefunden - Bluetooth-Audio nicht verfügbar." "Note: bluetoothctl (BlueZ) not found - Bluetooth audio not available.")"
    fi
}

#
# USB-Stick automatisch einhängen (fürs "Auf USB-Stick kopieren" im
# Aufnahmen-Modal).
#
# Eine udev-Regel löst bei jeder neu erkannten Partition einen
# systemd-Dienst aus, der sie - falls es sich um einen echten
# Wechseldatenträger handelt - unter einem festen Pfad einhängt
# (scripts/xrack-usb-mount.sh); beim Entfernen wird entsprechend
# wieder ausgehängt. Unterstützt genau einen angeschlossenen Stick
# gleichzeitig, ganz ohne Verzeichnisauswahl im Webinterface.
#
# RemainAfterExit=yes ist bei xrack-usb-mount@.service nötig, weil
# FUSE-Dateisysteme (NTFS über ntfs-3g) einen Hintergrundprozess
# starten, der die Einhängung am Leben hält. Ohne RemainAfterExit
# räumt systemd nach Ende des (Type=oneshot-)Skripts sofort die
# komplette Prozessgruppe auf und beendet dabei diesen Hintergrund-
# prozess gleich mit - der Stick wird dann im selben Moment wieder
# ausgehängt. Kernel-Dateisysteme (vfat/ext4) brauchen keinen
# Hintergrundprozess und sind davon nicht betroffen.
#
configure_usb_automount() {

    echo "$(L "XRack: USB-Stick-Automount wird eingerichtet..." "XRack: Setting up USB drive automount...")"

    chmod +x \
        "${INSTALL_DIR}/scripts/xrack-usb-mount.sh" \
        "${INSTALL_DIR}/scripts/xrack-usb-unmount.sh"

    SERVICE_UID="$(id -u "${XRACK_TARGET_USER}")"
    SERVICE_GID="$(id -g "${XRACK_TARGET_USER}")"

    sudo tee "/etc/systemd/system/xrack-usb-mount@.service" > /dev/null <<EOF
[Unit]
Description=XRack: USB-Stick automatisch einhängen (%i)
After=local-fs.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=${INSTALL_DIR}/scripts/xrack-usb-mount.sh %i ${SERVICE_UID} ${SERVICE_GID}
EOF

    sudo tee "/etc/systemd/system/xrack-usb-unmount.service" > /dev/null <<EOF
[Unit]
Description=XRack: USB-Stick aushängen

[Service]
Type=oneshot
ExecStart=${INSTALL_DIR}/scripts/xrack-usb-unmount.sh
EOF

    sudo tee "/etc/udev/rules.d/99-xrack-usb.rules" > /dev/null <<'EOF'
ACTION=="add", SUBSYSTEM=="block", KERNEL=="sd*", ENV{ID_FS_USAGE}=="filesystem", TAG+="systemd", ENV{SYSTEMD_WANTS}+="xrack-usb-mount@%k.service"
ACTION=="remove", SUBSYSTEM=="block", KERNEL=="sd*", RUN+="/usr/bin/systemctl --no-block start xrack-usb-unmount.service"
EOF

    sudo systemctl daemon-reload

    sudo udevadm control --reload-rules
    sudo udevadm trigger --subsystem-match=block >/dev/null 2>&1 || true
}

#
# sudo-Berechtigung für Herunterfahren, Dienst-Neustart und die
# WLAN-Einstellungen (Webinterface -> Einstellungen) einrichten.
#
# XRack läuft NICHT als root - der Dienst-Benutzer bekommt über eine
# dedizierte sudoers-Regel ausschließlich das Recht, den Pi
# herunterzufahren, sich selbst neu zu starten und die vier festen
# Wrapper-Skripte unter scripts/ auszuführen (die ihrerseits jeweils
# genau einen engen nmcli-Vorgang kapseln) - sonst nichts. Die Regel
# wird erst in eine temporäre Datei geschrieben und mit "visudo -c"
# geprüft, bevor sie aktiv wird, damit ein Tippfehler nicht die
# sudo-Konfiguration beschädigen kann.
#
configure_sudoers() {

    echo "$(L "XRack: sudo-Berechtigung fürs Herunterfahren/Neustarten/WLAN einrichten..." "XRack: Setting up sudo permission for shutdown/restart/Wi-Fi...")"

    SERVICE_USER="${XRACK_TARGET_USER}"

    chmod +x \
        "${INSTALL_DIR}/scripts/xrack-restart.sh" \
        "${INSTALL_DIR}/scripts/xrack-net-home.sh" \
        "${INSTALL_DIR}/scripts/xrack-net-ap.sh" \
        "${INSTALL_DIR}/scripts/xrack-bridge-toggle.sh" \
        "${INSTALL_DIR}/scripts/xrack-share-toggle.sh" \
        "${INSTALL_DIR}/scripts/xrack-dhcp-lease.sh" \
        "${INSTALL_DIR}/scripts/xrack-port-forward.sh" \
        "${INSTALL_DIR}/scripts/xrack-bt-power.sh" \
        "${INSTALL_DIR}/scripts/xrack-bt-pair.sh" \
        "${INSTALL_DIR}/scripts/xrack-bt-forget.sh" \
        "${INSTALL_DIR}/scripts/xrack-bt-disconnect.sh" \
        "${INSTALL_DIR}/scripts/xrack-usb-unmount.sh"

    SUDOERS_FILE="/etc/sudoers.d/xrack"
    SUDOERS_TMP="$(mktemp)"

    echo "${SERVICE_USER} ALL=(root) NOPASSWD: \
/usr/sbin/poweroff, /sbin/poweroff, /usr/sbin/shutdown, /sbin/shutdown, \
${INSTALL_DIR}/scripts/xrack-restart.sh, \
${INSTALL_DIR}/scripts/xrack-net-home.sh *, \
${INSTALL_DIR}/scripts/xrack-net-ap.sh *, \
${INSTALL_DIR}/scripts/xrack-bridge-toggle.sh *, \
${INSTALL_DIR}/scripts/xrack-share-toggle.sh *, \
${INSTALL_DIR}/scripts/xrack-dhcp-lease.sh *, \
${INSTALL_DIR}/scripts/xrack-port-forward.sh *, \
${INSTALL_DIR}/scripts/xrack-bt-power.sh *, \
${INSTALL_DIR}/scripts/xrack-bt-pair.sh, \
${INSTALL_DIR}/scripts/xrack-bt-forget.sh *, \
${INSTALL_DIR}/scripts/xrack-bt-disconnect.sh *, \
${INSTALL_DIR}/scripts/xrack-usb-unmount.sh" \
        > "${SUDOERS_TMP}"

    sudo visudo -cf "${SUDOERS_TMP}"

    sudo install -o root -g root -m 0440 "${SUDOERS_TMP}" "${SUDOERS_FILE}"

    rm -f "${SUDOERS_TMP}"
}

#
# systemd-Dienst einrichten (Autostart beim Booten).
#
configure_systemd_service() {

    echo "$(L "XRack: systemd-Dienst einrichten..." "XRack: Setting up systemd service...")"

    sudo tee /etc/systemd/system/xrack.service > /dev/null <<EOF
[Unit]
Description=XRack Audio Recorder/Player
After=network.target sound.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/.venv/bin/python ${INSTALL_DIR}/main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload

    sudo systemctl enable xrack.service
}

#
# Abschließende Zusammenfassung ausgeben.
#
print_summary() {

    echo ""
    echo "$(L "Fertig." "Done.")"
    echo ""
    echo "$(L "XRack startet ab jetzt automatisch beim Booten (systemd-Dienst 'xrack')." "XRack will now start automatically on boot (systemd service 'xrack').")"
    echo ""
    echo "$(L "Webinterface:             https://${XRACK_HOSTNAME}.local:${XRACK_PORT}" "Web interface:            https://${XRACK_HOSTNAME}.local:${XRACK_PORT}")"
    echo "$(L "                          (alternativ per IP: https://<ip-des-pi>:${XRACK_PORT})" "                          (or by IP: https://<pi-ip>:${XRACK_PORT})")"
    echo "$(L "Jetzt manuell starten:    sudo systemctl start xrack" "Start manually now:       sudo systemctl start xrack")"
    echo "$(L "Status ansehen:           sudo systemctl status xrack" "Check status:             sudo systemctl status xrack")"
    echo "$(L "Live-Logs ansehen:        journalctl -u xrack -f" "View live logs:           journalctl -u xrack -f")"
    echo ""
    echo "$(L "Hinweis: Das TLS-Zertifikat ist selbstsigniert - beim ersten" "Note: the TLS certificate is self-signed - on the first visit")"
    echo "$(L "Aufruf zeigt der Browser eine Sicherheitswarnung ('Erweitert' ->" "your browser will show a security warning ('Advanced' ->")"
    echo "$(L "'Trotzdem fortfahren'), danach nicht mehr." "'Proceed anyway'), never again after that.")"
    echo ""

    if [ -n "${XRACK_PIN_HASH}" ]; then
        echo "$(L "Einstellungen-Menü:       durch PIN geschützt (im Menü selbst änderbar)" "Settings menu:            PIN-protected (changeable in the menu itself)")"
    else
        echo "$(L "Einstellungen-Menü:       kein PIN-Schutz (im Menü selbst einrichtbar)" "Settings menu:            no PIN protection (can be set up in the menu itself)")"
    fi
    echo ""
    echo "$(L "Achtung: Wenn der Dienst laeuft, blockiert er Port ${XRACK_PORT} -" "Note: while the service is running it occupies port ${XRACK_PORT} -")"
    echo "$(L "dann NICHT zusaetzlich manuell 'python main.py' starten." "don't additionally start 'python main.py' manually.")"
    echo ""
    echo "$(L "Sprache/Port spaeter aendern: config/local.yaml bearbeiten und" "To change language/port later: edit config/local.yaml and")"
    echo "$(L "den Dienst neu starten (sudo systemctl restart xrack)." "restart the service (sudo systemctl restart xrack).")"
    echo "$(L "Hostname spaeter aendern:     sudo hostnamectl set-hostname <name>" "To change hostname later:    sudo hostnamectl set-hostname <name>")"
    echo "$(L "                              und /etc/hosts entsprechend anpassen." "                             and adjust /etc/hosts accordingly.")"

    if [ -n "${XRACK_WLAN_CLIENT_SSID}" ]; then
        echo ""
        echo "$(L "WLAN-Heimnetz:            '${XRACK_WLAN_CLIENT_SSID}' (Profil 'XRack-Home')" "Wi-Fi home network:       '${XRACK_WLAN_CLIENT_SSID}' (profile 'XRack-Home')")"
    fi

    if [ -n "${XRACK_WLAN_AP_SSID}" ]; then
        echo "$(L "WLAN-Access-Point:        '${XRACK_WLAN_AP_SSID}'" "Wi-Fi access point:       '${XRACK_WLAN_AP_SSID}'")"
    fi

    if [ "${XRACK_WLAN_BRIDGE}" = "ja" ]; then
        echo "$(L "Ethernet+AP gebridged:    eth0 (Mischpult) und Access Point im selben Netz (br0)" "Ethernet+AP bridged:      eth0 (mixing console) and access point on the same network (br0)")"
        echo "$(L "                          (wird erst nach einem Neustart aktiv, siehe unten)" "                          (only active after a restart, see below)")"
    fi

    if [ "${XRACK_WLAN_SHARE_READY}" = "ja" ]; then
        echo "$(L "Ethernet+Heimnetz-Freigabe verfügbar (im Einstellungen-Modal aktivierbar, aktuell aus)." "Ethernet+home network sharing available (enable it in the Settings modal, currently off).")"
    fi

    if [ -n "${XRACK_WLAN_CLIENT_SSID}" ] || [ -n "${XRACK_WLAN_AP_SSID}" ]; then
        echo "$(L "WLAN-Status pruefen:      nmcli connection show" "Check Wi-Fi status:       nmcli connection show")"
    fi
}

#
# Falls eine Ethernet+AP-Bridge eingerichtet wurde, wird sie erst
# jetzt - ganz am Ende, nach Sudoers/systemd-Setup - zur Aktivierung
# angeboten. Ein Neustart hier ist sicher, weil die komplette
# Installation zu diesem Zeitpunkt bereits fertig ist.
#
offer_reboot_for_bridge() {

    if [ "${XRACK_WLAN_BRIDGE}" = "ja" ]; then

        echo ""
        echo "$(L "Die Ethernet+AP-Bridge wird erst nach einem Neustart aktiv" "The Ethernet+AP bridge only becomes active after a restart")"
        echo "$(L "(damit eine laufende SSH-Verbindung über eth0 nicht mitten in" "(so a running SSH connection over eth0 doesn't drop in the")"
        echo "$(L "der Installation abbricht)." "middle of the installation).")"

        if [ -t 0 ]; then

            echo ""
            read -r -p "$(L "Jetzt neu starten? [j/N]: " "Restart now? [y/N]: ")" XRACK_REBOOT_NOW || true

            if confirm_yes "${XRACK_REBOOT_NOW}"; then
                echo "$(L "XRack: Neustart..." "XRack: Restarting...")"
                sudo reboot
            else
                echo "$(L "Bitte bei Gelegenheit manuell neu starten: sudo reboot" "Please restart manually when convenient: sudo reboot")"
            fi
        else
            echo "$(L "Bitte manuell neu starten, sobald es passt: sudo reboot" "Please restart manually whenever it suits you: sudo reboot")"
        fi
    fi
}

#
# Ablauf
#

confirm_start
choose_language
install_system_dependencies
configure_basic_settings
configure_hostname_and_avahi
generate_tls_certificate
configure_firewall
configure_wifi
configure_bluetooth
configure_usb_automount
configure_sudoers
configure_systemd_service
print_summary
offer_reboot_for_bridge
