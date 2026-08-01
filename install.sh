#!/usr/bin/env bash
#
# XRack Setup-Skript für Raspberry Pi OS / Debian.
#
# Installiert alle System- und Python-Abhängigkeiten und legt eine
# virtuelle Python-Umgebung (.venv) an.
#

set -e

echo "XRack: Systemabhängigkeiten installieren..."

sudo apt-get update

sudo apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    libasound2-dev \
    alsa-utils \
    ffmpeg

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
# sudo-Berechtigung für das Herunterfahren einrichten.
#
# XRack läuft NICHT als root - der Dienst-Benutzer bekommt über
# eine dedizierte sudoers-Regel ausschließlich das Recht, den Pi
# herunterzufahren, sonst nichts. Die Regel wird erst in eine
# temporäre Datei geschrieben und mit "visudo -c" geprüft, bevor
# sie aktiv wird, damit ein Tippfehler nicht die sudo-Konfiguration
# beschädigen kann.
#

echo "XRack: sudo-Berechtigung fürs Herunterfahren einrichten..."

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_USER="$(whoami)"

SUDOERS_FILE="/etc/sudoers.d/xrack"
SUDOERS_TMP="$(mktemp)"

echo "${SERVICE_USER} ALL=(root) NOPASSWD: /usr/sbin/poweroff, /sbin/poweroff, /usr/sbin/shutdown, /sbin/shutdown" \
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
