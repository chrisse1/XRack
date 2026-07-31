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

echo ""
echo "Fertig. Start mit:"
echo "  source .venv/bin/activate"
echo "  python main.py"
