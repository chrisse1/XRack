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
echo "Jetzt manuell starten:   sudo systemctl start xrack"
echo "Status ansehen:          sudo systemctl status xrack"
echo "Live-Logs ansehen:       journalctl -u xrack -f"
echo ""
echo "Achtung: Wenn der Dienst laeuft, blockiert er Port 8080 -"
echo "dann NICHT zusaetzlich manuell 'python main.py' starten."
