#!/usr/bin/env bash
#
# XRack Setup-Skript für Raspberry Pi OS / Debian.
#
# Installiert alle System- und Python-Abhängigkeiten und legt eine
# virtuelle Python-Umgebung (.venv) an.
#

set -e

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "XRack: Systemabhängigkeiten installieren..."

sudo apt-get update

sudo apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    libasound2-dev \
    alsa-utils \
    ffmpeg \
    bluez \
    bluez-alsa-utils \
    python3-dbus \
    python3-gi

echo "XRack: Python-Umgebung einrichten..."

python3 -m venv .venv

source .venv/bin/activate

pip install --upgrade pip

pip install -r requirements.txt

deactivate

#
# Sprache, Port und Hostname abfragen (config/local.yaml + System-
# Hostname).
#
# Läuft das Skript nicht interaktiv (z.B. per "curl | bash"), werden
# stillschweigend die Standardwerte (Deutsch, Port 8080, Hostname
# "xrack") verwendet.
#

XRACK_LANGUAGE="de"
XRACK_PORT="8080"
XRACK_HOSTNAME="xrack"
XRACK_WLAN_CLIENT_SSID=""
XRACK_WLAN_AP_SSID=""
XRACK_WLAN_BRIDGE=""

if [ -t 0 ]; then

    echo ""
    read -r -p "Sprache / Language [de/en] (Standard/default: de): " XRACK_LANGUAGE_INPUT || true

    if [ "${XRACK_LANGUAGE_INPUT}" = "en" ]; then
        XRACK_LANGUAGE="en"
    fi

    echo ""
    read -r -p "Port fürs Webinterface / Port for the web interface (Standard/default: 8080): " XRACK_PORT_INPUT || true

    if [ -n "${XRACK_PORT_INPUT}" ] && [ "${XRACK_PORT_INPUT}" -eq "${XRACK_PORT_INPUT}" ] 2>/dev/null; then
        XRACK_PORT="${XRACK_PORT_INPUT}"
    fi

    echo ""
    read -r -p "Hostname (Standard: xrack, erreichbar als http://<hostname>.local): " XRACK_HOSTNAME_INPUT || true

    if [ -n "${XRACK_HOSTNAME_INPUT}" ]; then
        if [[ "${XRACK_HOSTNAME_INPUT}" =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$ ]]; then
            XRACK_HOSTNAME="${XRACK_HOSTNAME_INPUT}"
        else
            echo "Ungültiger Hostname (nur Buchstaben, Ziffern, Bindestriche) - verwende 'xrack'."
        fi
    fi

fi

echo "XRack: Konfiguration wird geschrieben (Sprache: ${XRACK_LANGUAGE}, Port: ${XRACK_PORT})..."

cat > config/local.yaml <<EOF
application:
  language: "${XRACK_LANGUAGE}"

server:
  port: ${XRACK_PORT}
EOF

#
# Hostname setzen, damit der Pi im lokalen Netz per mDNS (Avahi)
# unter http://<hostname>.local erreichbar ist. Avahi kündigt den
# aktuellen System-Hostnamen automatisch an - hier wird nur der
# Hostname gesetzt und Avahi neu gestartet, damit er den neuen Namen
# sofort übernimmt (ohne Reboot).
#

echo "XRack: Hostname wird gesetzt (${XRACK_HOSTNAME})..."

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
    echo "Hinweis: avahi-daemon nicht gefunden - '${XRACK_HOSTNAME}.local' wird im Netzwerk nicht auffindbar sein."
fi

#
# Falls eine Firewall (ufw) aktiv ist, Freigaben für mDNS und das
# Webinterface ergänzen. Auf einem frischen Raspberry Pi OS/Debian
# ist standardmäßig keine Firewall aktiv - dieser Schritt greift nur,
# falls der Nutzer selbst ufw eingerichtet hat.
#

if command -v ufw >/dev/null 2>&1 && sudo ufw status | grep -q "^Status: active"; then
    echo "XRack: ufw ist aktiv - Firewall-Regeln werden ergänzt..."
    sudo ufw allow 5353/udp comment 'XRack mDNS (Avahi)'
    sudo ufw allow "${XRACK_PORT}/tcp" comment 'XRack Webinterface'
fi

#
# Optional: WLAN einrichten (Heimnetz-Client + eigener Access Point).
#
# Für Setups mit zwei WLAN-Interfaces, z.B. Onboard-WLAN als Client
# im Heimnetz (Fernzugriff auf XRack) und ein zusätzlicher USB-WLAN-
# Stick als eigener Access Point, über den z.B. eine Misch-App direkt
# mit dem Pi/Mischpult spricht - ganz ohne Router vor Ort. Komplett
# optional und nur bei interaktivem Lauf, per NetworkManager (nmcli).
#

valid_wifi_index() {
    local index="$1"
    local max="$2"
    [[ "${index}" =~ ^[0-9]+$ ]] && [ "${index}" -ge 1 ] && [ "${index}" -le "${max}" ]
}

if [ -t 0 ] && command -v nmcli >/dev/null 2>&1; then

    echo ""
    read -r -p "WLAN einrichten - Heimnetz-Verbindung + eigener Access Point? [j/N]: " XRACK_WLAN_SETUP || true

    if [ "${XRACK_WLAN_SETUP}" = "j" ] || [ "${XRACK_WLAN_SETUP}" = "J" ]; then

        #
        # WLAN-Land setzen. Ohne gesetztes Regulierungsgebiet bleibt
        # WLAN auf frisch aufgesetzten Raspberry Pis oft per rfkill
        # soft-blockiert (Geräte existieren, sind aber "nicht
        # verfügbar") - das kostet sonst viel Fehlersuche.
        #

        echo ""
        read -r -p "WLAN-Land (2-stelliger ISO-Code, z.B. DE/AT/CH/US/GB) - nötig, damit WLAN nicht per rfkill blockiert bleibt: " XRACK_WLAN_COUNTRY_INPUT || true
        XRACK_WLAN_COUNTRY="$(echo "${XRACK_WLAN_COUNTRY_INPUT}" | tr '[:lower:]' '[:upper:]')"

        if [[ "${XRACK_WLAN_COUNTRY}" =~ ^[A-Z]{2}$ ]]; then

            echo "XRack: WLAN-Land wird gesetzt (${XRACK_WLAN_COUNTRY})..."

            if command -v raspi-config >/dev/null 2>&1; then
                sudo raspi-config nonint do_wifi_country "${XRACK_WLAN_COUNTRY}"
            else
                sudo rfkill unblock wifi
                sudo iw reg set "${XRACK_WLAN_COUNTRY}" || true
                echo "Hinweis: raspi-config nicht gefunden - WLAN-Land ist damit ggf. nicht dauerhaft gesetzt (nach einem Neustart mit 'rfkill list' prüfen)."
            fi
        else
            echo "Ungültiger oder leerer Ländercode - WLAN-Land wird übersprungen (WLAN kann per rfkill blockiert bleiben, siehe 'rfkill list')."
        fi

        mapfile -t WIFI_INTERFACES < <(nmcli -t -f DEVICE,TYPE device status | awk -F: '$2=="wifi"{print $1}')

        if [ "${#WIFI_INTERFACES[@]}" -lt 2 ]; then
            echo "Es wurden nur ${#WIFI_INTERFACES[@]} WLAN-Interface(s) gefunden - für Client + Access Point werden zwei benötigt. WLAN-Setup übersprungen."
        else

            echo ""
            echo "Gefundene WLAN-Interfaces:"
            for i in "${!WIFI_INTERFACES[@]}"; do
                echo "  $((i + 1))) ${WIFI_INTERFACES[$i]}"
            done

            echo ""
            read -r -p "Welches Interface soll sich mit deinem Heimnetz verbinden (Nummer)? " CLIENT_INDEX || true
            read -r -p "Welches Interface soll den Access Point aufspannen (Nummer)? " AP_INDEX || true

            CLIENT_IFACE=""
            AP_IFACE=""

            if valid_wifi_index "${CLIENT_INDEX}" "${#WIFI_INTERFACES[@]}" \
                && valid_wifi_index "${AP_INDEX}" "${#WIFI_INTERFACES[@]}" \
                && [ "${CLIENT_INDEX}" != "${AP_INDEX}" ]; then

                CLIENT_IFACE="${WIFI_INTERFACES[$((CLIENT_INDEX - 1))]}"
                AP_IFACE="${WIFI_INTERFACES[$((AP_INDEX - 1))]}"
            fi

            if [ -z "${CLIENT_IFACE}" ] || [ -z "${AP_IFACE}" ]; then
                echo "Ungültige oder gleiche Auswahl - WLAN-Setup übersprungen."
            else

                echo ""
                read -r -p "Heimnetz-SSID: " HOME_SSID || true
                read -r -s -p "Heimnetz-Passwort: " HOME_PASSWORD || true
                echo ""
                read -r -s -p "Heimnetz-Passwort (Wiederholung): " HOME_PASSWORD_CONFIRM || true
                echo ""

                echo ""
                read -r -p "Name des Access Points (Standard: XRack): " AP_SSID_INPUT || true
                AP_SSID="${AP_SSID_INPUT:-XRack}"
                read -r -s -p "Passwort für den Access Point (mind. 8 Zeichen): " AP_PASSWORD || true
                echo ""
                read -r -s -p "Passwort für den Access Point (Wiederholung): " AP_PASSWORD_CONFIRM || true
                echo ""

                if [ "${HOME_PASSWORD}" != "${HOME_PASSWORD_CONFIRM}" ]; then
                    echo "Die beiden Heimnetz-Passwörter stimmen nicht überein - Heimnetz-Verbindung wird übersprungen."
                    HOME_PASSWORD=""
                fi

                if [ "${AP_PASSWORD}" != "${AP_PASSWORD_CONFIRM}" ]; then
                    echo "Die beiden Access-Point-Passwörter stimmen nicht überein - Access Point wird übersprungen."
                    AP_PASSWORD=""
                fi

                if [ -z "${HOME_SSID}" ] || [ "${#HOME_PASSWORD}" -lt 8 ]; then
                    echo "Heimnetz-SSID fehlt oder Passwort fehlt/zu kurz (mind. 8 Zeichen) - Heimnetz-Verbindung übersprungen."
                else

                    echo "XRack: Verbinde ${CLIENT_IFACE} mit '${HOME_SSID}'..."
                    echo "Hinweis: Falls du gerade über dieses Interface per WLAN verbunden bist, kann die Verbindung kurz unterbrochen werden."

                    sudo nmcli connection delete "XRack-Home" >/dev/null 2>&1 || true

                    if sudo nmcli connection add type wifi ifname "${CLIENT_IFACE}" con-name "XRack-Home" \
                        ssid "${HOME_SSID}" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "${HOME_PASSWORD}" \
                        connection.autoconnect yes >/dev/null; then

                        XRACK_WLAN_CLIENT_SSID="${HOME_SSID}"

                        sudo nmcli connection up "XRack-Home" ifname "${CLIENT_IFACE}" \
                            || echo "Warnung: Verbindung zu '${HOME_SSID}' konnte nicht sofort hergestellt werden (SSID/Passwort prüfen)."
                    else
                        echo "Warnung: WLAN-Client-Profil konnte nicht angelegt werden."
                    fi
                fi

                if [ "${#AP_PASSWORD}" -lt 8 ]; then
                    echo "Access-Point-Passwort fehlt/zu kurz (mind. 8 Zeichen) - Access Point übersprungen."
                else

                    echo "XRack: Access Point '${AP_SSID}' wird auf ${AP_IFACE} eingerichtet..."

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
                            || echo "Warnung: Access Point konnte nicht gestartet werden."

                        #
                        # Optional: Ethernet-Interface (z.B. das per Kabel
                        # angeschlossene Mischpult) mit dem Access Point
                        # bridgen, damit Steuerungs-Apps (z.B. Mixing
                        # Station) das Pult über den AP finden - beide
                        # landen dann im selben Netz statt in getrennten,
                        # sich gegenseitig nicht sehenden Subnetzen.
                        #

                        echo ""
                        read -r -p "Ethernet-Interface (z.B. Mischpult an eth0) mit dem Access Point bridgen, damit Apps es finden? [J/n]: " XRACK_BRIDGE_SETUP || true

                        if [ "${XRACK_BRIDGE_SETUP}" != "n" ] && [ "${XRACK_BRIDGE_SETUP}" != "N" ]; then

                            echo "XRack: Bridge aus eth0 und ${AP_IFACE} wird vorbereitet..."
                            echo "Hinweis: Wird jetzt nur angelegt, nicht sofort aktiviert - viele"
                            echo "konfigurieren den Pi anfangs per SSH über eth0, das würde sonst"
                            echo "genau jetzt abbrechen. Aktiv wird die Bridge erst nach einem"
                            echo "Neustart (Abfrage dazu kommt ganz am Ende)."

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
                                echo "Warnung: Bridge konnte nicht eingerichtet werden."
                            fi
                        fi
                    else
                        echo "Warnung: Access-Point-Profil konnte nicht angelegt werden."
                    fi
                fi

            fi
        fi

    fi

elif [ -t 0 ]; then
    echo ""
    echo "Hinweis: nmcli (NetworkManager) nicht gefunden - WLAN-Setup (Heimnetz + Access Point) übersprungen."
fi

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

if command -v bluetoothctl >/dev/null 2>&1; then

    echo "XRack: Bluetooth-Audio (bluealsa) wird eingerichtet..."

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
    echo "Hinweis: bluetoothctl (BlueZ) nicht gefunden - Bluetooth-Audio nicht verfügbar."
fi

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

echo "XRack: sudo-Berechtigung fürs Herunterfahren/Neustarten/WLAN einrichten..."

SERVICE_USER="$(whoami)"

chmod +x \
    "${INSTALL_DIR}/scripts/xrack-restart.sh" \
    "${INSTALL_DIR}/scripts/xrack-net-home.sh" \
    "${INSTALL_DIR}/scripts/xrack-net-ap.sh" \
    "${INSTALL_DIR}/scripts/xrack-bridge-toggle.sh" \
    "${INSTALL_DIR}/scripts/xrack-bt-power.sh" \
    "${INSTALL_DIR}/scripts/xrack-bt-pair.sh" \
    "${INSTALL_DIR}/scripts/xrack-bt-forget.sh"

SUDOERS_FILE="/etc/sudoers.d/xrack"
SUDOERS_TMP="$(mktemp)"

echo "${SERVICE_USER} ALL=(root) NOPASSWD: \
/usr/sbin/poweroff, /sbin/poweroff, /usr/sbin/shutdown, /sbin/shutdown, \
${INSTALL_DIR}/scripts/xrack-restart.sh, \
${INSTALL_DIR}/scripts/xrack-net-home.sh *, \
${INSTALL_DIR}/scripts/xrack-net-ap.sh *, \
${INSTALL_DIR}/scripts/xrack-bridge-toggle.sh *, \
${INSTALL_DIR}/scripts/xrack-bt-power.sh *, \
${INSTALL_DIR}/scripts/xrack-bt-pair.sh, \
${INSTALL_DIR}/scripts/xrack-bt-forget.sh *" \
    > "${SUDOERS_TMP}"

sudo visudo -cf "${SUDOERS_TMP}"

sudo install -o root -g root -m 0440 "${SUDOERS_TMP}" "${SUDOERS_FILE}"

rm -f "${SUDOERS_TMP}"

#
# systemd-Dienst einrichten (Autostart beim Booten).
#

echo "XRack: systemd-Dienst einrichten..."

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

echo ""
echo "Fertig."
echo ""
echo "XRack startet ab jetzt automatisch beim Booten (systemd-Dienst 'xrack')."
echo ""
echo "Webinterface:             http://${XRACK_HOSTNAME}.local:${XRACK_PORT}"
echo "                          (alternativ per IP: http://<ip-des-pi>:${XRACK_PORT})"
echo "Jetzt manuell starten:    sudo systemctl start xrack"
echo "Status ansehen:           sudo systemctl status xrack"
echo "Live-Logs ansehen:        journalctl -u xrack -f"
echo ""
echo "Achtung: Wenn der Dienst laeuft, blockiert er Port ${XRACK_PORT} -"
echo "dann NICHT zusaetzlich manuell 'python main.py' starten."
echo ""
echo "Sprache/Port spaeter aendern: config/local.yaml bearbeiten und"
echo "den Dienst neu starten (sudo systemctl restart xrack)."
echo "Hostname spaeter aendern:     sudo hostnamectl set-hostname <name>"
echo "                              und /etc/hosts entsprechend anpassen."

if [ -n "${XRACK_WLAN_CLIENT_SSID}" ]; then
    echo ""
    echo "WLAN-Heimnetz:            '${XRACK_WLAN_CLIENT_SSID}' (Profil 'XRack-Home')"
fi

if [ -n "${XRACK_WLAN_AP_SSID}" ]; then
    echo "WLAN-Access-Point:        '${XRACK_WLAN_AP_SSID}'"
fi

if [ "${XRACK_WLAN_BRIDGE}" = "ja" ]; then
    echo "Ethernet+AP gebridged:    eth0 (Mischpult) und Access Point im selben Netz (br0)"
    echo "                          (wird erst nach einem Neustart aktiv, siehe unten)"
fi

if [ -n "${XRACK_WLAN_CLIENT_SSID}" ] || [ -n "${XRACK_WLAN_AP_SSID}" ]; then
    echo "WLAN-Status pruefen:      nmcli connection show"
fi

#
# Falls eine Ethernet+AP-Bridge eingerichtet wurde, wird sie erst
# jetzt - ganz am Ende, nach Sudoers/systemd-Setup - zur Aktivierung
# angeboten. Ein Neustart hier ist sicher, weil die komplette
# Installation zu diesem Zeitpunkt bereits fertig ist.
#

if [ "${XRACK_WLAN_BRIDGE}" = "ja" ]; then

    echo ""
    echo "Die Ethernet+AP-Bridge wird erst nach einem Neustart aktiv"
    echo "(damit eine laufende SSH-Verbindung über eth0 nicht mitten in"
    echo "der Installation abbricht)."

    if [ -t 0 ]; then

        echo ""
        read -r -p "Jetzt neu starten? [j/N]: " XRACK_REBOOT_NOW || true

        if [ "${XRACK_REBOOT_NOW}" = "j" ] || [ "${XRACK_REBOOT_NOW}" = "J" ]; then
            echo "XRack: Neustart..."
            sudo reboot
        else
            echo "Bitte bei Gelegenheit manuell neu starten: sudo reboot"
        fi
    else
        echo "Bitte manuell neu starten, sobald es passt: sudo reboot"
    fi
fi
