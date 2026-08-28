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

        #
        # Noch vor der Sprachwahl, deshalb zweisprachig
        # untereinander. Der Hinweis auf die Netzwerkkonfiguration
        # gehoert an den Anfang: Wer den Pi gerade per WLAN oder ueber
        # das eingerichtete Kabelnetz erreicht, soll VOR der
        # Installation wissen, dass sich daran etwas aendert.
        #
        echo "Willkommen zum XRack Setup!"
        echo ""
        echo "Dieser Installer installiert XRack auf Ihrem System."
        echo "Dabei wird eine eventuelle Netzwerkkonfiguration verworfen"
        echo "und auf die Beduerfnisse von XRack angepasst."
        echo ""
        echo "This installer will install XRack on this system. Any existing"
        echo "network configuration will be replaced by XRack's own."
        echo ""
        read -r -p "Moechten Sie fortfahren? / Continue? [J/n]: " XRACK_CONFIRM_START || true

        if [ "$(lower "${XRACK_CONFIRM_START}")" = "n" ]; then
            echo "Abgebrochen - es wurde nichts geaendert."
            exit 0
        fi
    fi
}

#
# Fuehrt einen Befehl aus und zeigt solange drei nacheinander
# erscheinende Punkte.
#
# Wozu: apt und pip brauchen Minuten und geben dabei nichts aus (ihre
# Ausgabe ist unterdrueckt, sonst rauscht sie den Ablauf zu). Ein
# stehender Text sieht dann aus, als haenge das Skript. Die Punkte
# zeigen, dass noch etwas passiert.
#
# $1 = Text davor, Rest = der Befehl.
#
mit_punkten() {

    local text="$1"
    shift

    printf '%s' "${text}"

    #
    # Nicht interaktiv (z.B. in einer Protokolldatei) waeren die
    # Punkte nur Zeichensalat - dann einfach ausfuehren.
    #
    if [ ! -t 1 ]; then
        echo ""
        "$@"
        return $?
    fi

    "$@" &
    local pid=$!

    while kill -0 "${pid}" 2>/dev/null; do
        for _ in 1 2 3; do
            kill -0 "${pid}" 2>/dev/null || break
            printf '.'
            sleep 1
        done
        kill -0 "${pid}" 2>/dev/null || break
        printf '\b\b\b   \b\b\b'
    done

    wait "${pid}"
    local ergebnis=$?

    echo ""

    return ${ergebnis}
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

    #
    # Zuerst die sudo-Berechtigung im Vordergrund holen: Weiter unten
    # laeuft apt im Hintergrund (wegen der Punkte), und eine
    # Passwortabfrage waere dort unsichtbar - das Skript schiene zu
    # haengen.
    #
    sudo -v

    systempakete() {

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
        iptables \
        iw \
        hostapd \
        avahi-daemon > /dev/null
    }

    mit_punkten \
        "$(L "XRack: Systemabhängigkeiten werden installiert" "XRack: Installing system dependencies")" \
        systempakete

    #
    # Die Python-Umgebung in einem Rutsch, damit die Punkte ueber den
    # ganzen Vorgang laufen und nicht dreimal neu anfangen.
    #
    python_umgebung() {
        python3 -m venv .venv
        # shellcheck disable=SC1091
        source .venv/bin/activate
        pip install --upgrade pip -q
        pip install -r requirements.txt -q
        deactivate
    }

    mit_punkten \
        "$(L "XRack: Python-Umgebung wird eingerichtet" "XRack: Setting up Python environment")" \
        python_umgebung
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
        #
        # Bewusst ohne ".local": Das funktioniert nur, wenn im Netz
        # etwas mDNS aufloest - manche Router und manche Handys tun
        # das nicht. Wer es kann, findet es trotzdem; wer nicht, wird
        # sonst mit einer Adresse in die Irre geschickt, die bei ihm
        # nie geht.
        #
        read -r -p "$(L "Hostname (Standard: xrack): " "Hostname (default: xrack): ")" XRACK_HOSTNAME_INPUT || true

        if [ -n "${XRACK_HOSTNAME_INPUT}" ]; then
            if [[ "${XRACK_HOSTNAME_INPUT}" =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$ ]]; then
                XRACK_HOSTNAME="${XRACK_HOSTNAME_INPUT}"
            else
                echo "$(L "Ungültiger Hostname (nur Buchstaben, Ziffern, Bindestriche) - verwende 'xrack'." "Invalid hostname (letters, digits, hyphens only) - using 'xrack'.")"
            fi
        fi

        echo ""
        echo "$(L "Eine 4-stellige PIN schützt das Einstellungen-Menü vor unbefugtem Zugriff. Sie lässt sich später jederzeit im Einstellungen-Menü selbst ändern." "A 4-digit PIN protects the settings menu from unauthorized access. You can change it any time later in the settings menu itself.")"
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

    #
    # avahi beantwortet Anfragen nach "<hostname>.local" im lokalen
    # Netz. Das Paket wird seit dieser Fassung ausdruecklich
    # mitinstalliert - vorher hat XRack nur eingeschaltet, was
    # zufaellig schon da war, und auf einem schlanken System war das
    # eben nichts. Der Hinweis unten bleibt fuer den Fall, dass die
    # Installation des Pakets scheitert.
    #
    if command -v avahi-daemon >/dev/null 2>&1; then

        sudo systemctl enable avahi-daemon >/dev/null 2>&1 || true
        sudo systemctl restart avahi-daemon

        #
        # avahi liest den Hostnamen beim Start. Er wurde gerade eben
        # geaendert - ohne den Neustart oben meldete sich der Pi
        # weiter unter dem alten Namen.
        #
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
# ------------------------------------------------------------------
# Access Point: hostapd statt NetworkManager
# ------------------------------------------------------------------
#
# Warum dieser Umbau:
#
# NetworkManager spannt seinen Hotspot mit der AP-Betriebsart von
# wpa_supplicant auf. Die ist dort Beiwerk - wpa_supplicant ist zum
# Verbinden mit fremden Netzen gebaut, nicht zum Betreiben eines
# eigenen. Im Betrieb sah das so aus: Mal verbindet sich das Handy
# sofort, mal muss man das Passwort zehnmal eingeben. Im Protokoll
# stand dazu nicht etwa ein Passwort- oder Schluesselfehler, sondern
#
#     handle_assoc_cb: STA ... not found
#
# Der Anmeldeversuch kam also an, nur war der Client zu diesem
# Zeitpunkt intern schon wieder vergessen - ein Wettlauf. Fuer den
# Nutzer sieht das aus wie ein falsches Passwort.
#
# hostapd ist das Programm, fuer das AP-Betrieb der Hauptzweck ist
# (wpa_supplicants AP-Code stammt urspruenglich sogar daher). Damit
# faellt die Ursache weg, statt sie zu umgehen.
#
# Aufbau danach:
#
#   hostapd  ->  Funk und Verschluesselung auf dem AP-Interface
#   br0      ->  Layer 2: der Access Point immer, eth0 (Mischpult)
#                zuschaltbar
#   NM       ->  IP, DHCP und NAT auf br0 ("ipv4.method shared"),
#                ausserdem Heimnetz-Client und Kabelverbindung
#
# Wichtig daran: Der Access Point haengt ab jetzt IMMER in der
# Bridge, auch wenn gerade kein Ethernet zugeschaltet ist. Das
# Umschalten "Konsole ueber XRacks Access Point erreichbar" haengt
# damit nur noch eth0 in die Bridge ein oder aus - der Funkbetrieb
# wird dabei nicht mehr angefasst. Vorher wurde dafuer der Access
# Point selbst umkonfiguriert und neu gestartet; daher kamen der
# Neustartbedarf beim Umschalten und der Zustand "beide Schalter an"
# nach dem Booten.
#
# Damit hostapd das Interface bekommt, wird es NetworkManager
# ausdruecklich entzogen (unmanaged-devices) - sonst wuerden beide
# gleichzeitig darauf funken wollen.
#

#
# Die Bridge anlegen, in der der Access Point lebt.
#
# eth0 wird hier bewusst NICHT aktiviert: Wer den Pi gerade per SSH
# ueber eth0 einrichtet, verloere sonst mitten in der Installation
# die Verbindung. Das eth0-Profil der Bridge wird nur angelegt und
# bleibt aus, bis es im Einstellungen-Menue zugeschaltet wird
# (scripts/xrack-bridge-toggle.sh).
#
setup_ap_bridge() {

    #
    # Feste Adresse statt NetworkManager die Range frei waehlen zu
    # lassen: Sonst verschiebt sich das Subnetz je nach Reihenfolge
    # anderer "shared"-Verbindungen zwischen 10.42.0.0/24 und
    # 10.42.1.0/24, und die Portweiterleitung
    # (scripts/xrack-port-forward.sh) zeigt auf eine veraltete
    # Konsolen-IP.
    #
    if ! nmcli -t -f NAME connection show | grep -qx "XRack-Bridge"; then

        sudo nmcli connection add type bridge ifname br0 con-name "XRack-Bridge" \
            connection.autoconnect yes >/dev/null || return 1
    fi

    sudo nmcli connection modify "XRack-Bridge" \
        ipv4.method shared \
        ipv4.addresses 10.42.0.1/24 \
        bridge.stp no \
        connection.autoconnect yes || return 1

    if ! nmcli -t -f NAME connection show | grep -qx "XRack-Bridge-eth0"; then

        sudo nmcli connection add type ethernet ifname eth0 con-name "XRack-Bridge-eth0" \
            master "XRack-Bridge" slave-type bridge \
            connection.autoconnect no >/dev/null || return 1
    fi

    return 0
}

#
# Fremde WLAN-Profile stilllegen.
#
# Raspberry Pi OS legt beim Schreiben der Speicherkarte auf Wunsch
# schon ein WLAN-Profil an (meist "preconfigured"), und wer den Pi
# vorher von Hand ins Heimnetz gebracht hat, hat ebenfalls eines.
# Beide bleiben sonst neben XRack-Home stehen, alle mit
# "autoconnect yes" - welches nach einem Neustart gewinnt,
# entscheidet NetworkManager dann nach Kriterien, die von aussen wie
# Zufall aussehen. Genau das ist der Grund, warum ein Geraet
# manchmal im falschen Netz aufwacht.
#
# Abgeschaltet wird nur das selbsttaetige Verbinden - geloescht wird
# nichts: Wer gerade ueber genau dieses Profil per SSH verbunden ist,
# soll die Sitzung nicht verlieren (autoconnect wirkt erst beim
# naechsten Verbindungsaufbau), und wer es spaeter wieder braucht,
# findet es noch vor.
#
disable_foreign_wifi_profiles() {

    while IFS=: read -r name typ; do

        [ "${typ}" = "802-11-wireless" ] || continue
        [ "${name}" = "XRack-Home" ] && continue
        [ "${name}" = "XRack-AP" ] && continue

        if [ "$(nmcli -g connection.autoconnect connection show "${name}" 2>/dev/null)" = "no" ]; then
            continue
        fi

        echo "$(L "XRack: WLAN-Profil '${name}' verbindet sich nicht mehr von selbst (bleibt aber erhalten)." "XRack: Wi-Fi profile '${name}' will no longer connect on its own (it is kept, though).")"

        sudo nmcli connection modify "${name}" connection.autoconnect no >/dev/null 2>&1 || true

    done < <(nmcli -t -f NAME,TYPE connection show 2>/dev/null)
}

#
# Optional: WLAN einrichten (Heimnetz-Client + eigener Access Point).
#
# Für Setups mit zwei WLAN-Interfaces, z.B. Onboard-WLAN als Client
# im Heimnetz (Fernzugriff auf XRack) und ein zusätzlicher USB-WLAN-
# Stick als eigener Access Point, über den z.B. eine Misch-App direkt
# mit dem Pi/Mischpult spricht - ganz ohne Router vor Ort. Komplett
# optional und nur bei interaktivem Lauf.
#
# Der Heimnetz-Client läuft über NetworkManager (nmcli), der Access
# Point über hostapd - siehe den Kommentarblock weiter oben.
#
configure_wifi() {

    XRACK_WLAN_CLIENT_SSID=""
    XRACK_WLAN_AP_SSID=""
    XRACK_WLAN_BRIDGE=""
    XRACK_WLAN_SHARE_READY=""
    XRACK_WLAN_COUNTRY=""

    if ! command -v nmcli >/dev/null 2>&1; then
        echo ""
        echo "$(L "Hinweis: nmcli (NetworkManager) nicht gefunden - Netzwerk-Einrichtung übersprungen." "Note: nmcli (NetworkManager) not found - network setup skipped.")"
        return 0
    fi

    #
    # Das Grundgeruest wird IMMER angelegt, unabhaengig von den
    # Antworten unten: die Bridge br0, ihr eth0-Anschluss und das
    # Profil fuer die Heimnetz-Freigabe.
    #
    # Der Grund ist der Nachruestfall: Wer hier "kein Access Point"
    # waehlt und es sich spaeter anders ueberlegt, soll das im
    # Einstellungen-Menue erledigen koennen, ohne install.sh noch
    # einmal durchlaufen zu lassen. Dafuer muss alles, was root-Rechte
    # braucht, jetzt schon stehen - anlegen kostet nichts, aktiv wird
    # davon nichts.
    #
    if setup_ap_bridge; then
        XRACK_WLAN_BRIDGE="ja"
    else
        echo "$(L "Warnung: Die Bridge br0 konnte nicht angelegt werden." "Warning: could not create the br0 bridge.")"
    fi

    if setup_share_profile; then
        XRACK_WLAN_SHARE_READY="ja"
    fi

    #
    # Zuletzt, damit es auch dann steht, wenn oben etwas schiefging.
    #
    if ! setup_wired_profile; then
        echo "$(L "Warnung: Das Profil für die normale Kabelverbindung konnte nicht angelegt werden." "Warning: could not create the profile for the normal wired connection.")"
    fi

    if [ ! -t 0 ]; then
        return 0
    fi

    #
    # Die drei Betriebsarten einmal erklaeren. Wer das hier liest,
    # trifft gleich zwei Entscheidungen und sollte wissen, wofuer.
    #
    echo ""
    echo "$(L "Netzwerkkonfiguration" "Network configuration")"
    echo "$(L "XRack kann in drei Modi betrieben werden:" "XRack can be run in three modes:")"
    echo ""
    echo "$(L "1. XRack und Mischpult per LAN an einem Router" "1. XRack and mixer connected by LAN to one router")"
    echo "$(L "2. XRack spannt einen Access Point auf, das Mischpult hängt per" "2. XRack runs an access point, the mixer is connected to the")"
    echo "$(L "   LAN-Kabel am Raspberry Pi (dafür wird ein geeigneter" "   Raspberry Pi by LAN cable (this needs a suitable USB Wi-Fi")"
    echo "$(L "   USB-WLAN-Stick gebraucht)" "   adapter)")"
    echo "$(L "3. XRack verbindet sich per WLAN mit einem bestehenden Netzwerk," "3. XRack connects to an existing Wi-Fi network, the mixer is")"
    echo "$(L "   das Mischpult hängt per LAN-Kabel am Raspberry Pi" "   connected to the Raspberry Pi by LAN cable")"
    echo ""
    echo "$(L "Sie können jetzt die Optionen 2 und 3 einrichten. Wenn Sie diesen" "You can set up options 2 and 3 now. If you skip this step, all")"
    echo "$(L "Schritt überspringen, lässt sich alles später im Einstellungen-Menü" "settings can be made later in the settings menu - a second run of")"
    echo "$(L "nachholen - ein erneuter Lauf von install.sh ist dafür nicht nötig." "install.sh is not needed for that.")"
    echo ""
    echo "$(L "!ACHTUNG! Sind Sie gerade per WLAN mit Ihrem Raspberry Pi verbunden," "!CAUTION! If you are currently connected to your Raspberry Pi over")"
    echo "$(L "sollten Sie die WLAN-Konfiguration unbedingt jetzt durchführen." "Wi-Fi, you should definitely do the Wi-Fi configuration now.")"

    # ----------------------------------------------------------------
    # Teil 1: Verbindung ins bestehende Netzwerk
    # ----------------------------------------------------------------

    echo ""
    read -r -p "$(L "Wollen Sie eine WLAN-Verbindung zu einem bestehenden Netzwerk einrichten? [J/n]: " "Do you want to set up a Wi-Fi connection to an existing network? [Y/n]: ")" XRACK_WLAN_SETUP || true

    if [ "$(lower "${XRACK_WLAN_SETUP}")" != "n" ]; then
        configure_wifi_client
    fi

    # ----------------------------------------------------------------
    # Teil 2: eigener Access Point
    # ----------------------------------------------------------------

    echo ""
    read -r -p "$(L "Wollen Sie einen Access Point einrichten? [J/n]: " "Do you want to set up an access point? [Y/n]: ")" XRACK_AP_SETUP || true

    if [ "$(lower "${XRACK_AP_SETUP}")" != "n" ]; then
        configure_access_point
    fi
}

#
# Teil 1: Verbindung ins bestehende Netzwerk.
#
# Welches Funkgeraet das macht, wird nicht mehr gefragt - es ist
# immer das eingebaute (siehe scripts/xrack-wifi-iface.sh).
#
configure_wifi_client() {

    echo ""
    echo "$(L "WLAN-Einrichtung" "Wi-Fi setup")"

    CLIENT_IFACE="$("${INSTALL_DIR}/scripts/xrack-wifi-iface.sh" client)"

    if [ -z "${CLIENT_IFACE}" ]; then
        echo "$(L "Kein WLAN-Gerät gefunden - dieser Schritt wird übersprungen." "No Wi-Fi device found - skipping this step.")"
        return 0
    fi

    frage_wlan_land

    echo ""
    read -r -p "$(L "WLAN-SSID: " "Wi-Fi SSID: ")" HOME_SSID || true
    read_confirmed_secret "$(L "WLAN-Passwort (mind. 8 Zeichen)" "Wi-Fi password (min. 8 characters)")" 8 HOME_PASSWORD

    if [ -z "${HOME_SSID}" ] || [ "${#HOME_PASSWORD}" -lt 8 ]; then
        echo "$(L "SSID fehlt oder Passwort fehlt/zu kurz (mind. 8 Zeichen) - WLAN-Verbindung übersprungen." "SSID missing, or password missing/too short (min. 8 characters) - Wi-Fi connection skipped.")"
        return 0
    fi

    echo ""
    echo "$(L "XRack: Verbinde ${CLIENT_IFACE} mit '${HOME_SSID}'..." "XRack: Connecting ${CLIENT_IFACE} to '${HOME_SSID}'...")"
    echo "$(L "Hinweis: Falls Sie gerade über dieses Interface per WLAN verbunden sind, kann die Verbindung kurz unterbrochen werden." "Note: if you are currently connected over this interface, the connection may briefly drop.")"

    sudo nmcli connection delete "XRack-Home" >/dev/null 2>&1 || true

    if ! sudo nmcli connection add type wifi ifname "${CLIENT_IFACE}" con-name "XRack-Home" \
        ssid "${HOME_SSID}" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "${HOME_PASSWORD}" \
        connection.autoconnect yes >/dev/null; then

        echo "$(L "Warnung: WLAN-Profil konnte nicht angelegt werden." "Warning: could not create the Wi-Fi profile.")"
        return 0
    fi

    XRACK_WLAN_CLIENT_SSID="${HOME_SSID}"

    #
    # Alte WLAN-Profile aus dem Weg raeumen - sonst konkurrieren sie
    # mit XRack-Home um dasselbe Funkgeraet.
    #
    disable_foreign_wifi_profiles

    sudo nmcli connection up "XRack-Home" ifname "${CLIENT_IFACE}" \
        || echo "$(L "Warnung: Verbindung zu '${HOME_SSID}' konnte nicht sofort hergestellt werden (SSID/Passwort prüfen)." "Warning: could not connect to '${HOME_SSID}' immediately (check SSID/password).")"
}

#
# Das WLAN-Land.
#
# Ohne richtige Funkregion bleibt das Funkgeraet per rfkill gesperrt,
# und dem Access Point fehlen die 5-GHz-Kanaele - er laeuft dann
# bestenfalls auf dem zugestellten 2,4-GHz-Band.
#
# Gefragt wird nur einmal, egal ueber welchen der beiden Zweige man
# hier ankommt: Wer die WLAN-Verbindung eingerichtet hat, hat es
# schon beantwortet. Wer sie uebersprungen und nur einen Access Point
# gewaehlt hat, wird hier gefragt - sonst haette genau dieser Weg
# keine Funkregion, und das faellt erst auf, wenn der Access Point
# nicht so funkt wie er soll.
#
frage_wlan_land() {

    if [ -n "${XRACK_WLAN_COUNTRY}" ]; then
        return 0
    fi

    local attempt eingabe

    for attempt in 1 2 3; do

        echo ""
        read -r -p "$(L "WLAN-Land (2-stelliger ISO-Code, z.B. DE/AT/CH/US/GB, leer = überspringen): " "Wi-Fi country (2-letter ISO code, e.g. DE/AT/CH/US/GB, empty = skip): ")" eingabe || true

        if [ -z "${eingabe}" ]; then
            return 0
        fi

        XRACK_WLAN_COUNTRY="$(printf '%s' "${eingabe}" | tr '[:lower:]' '[:upper:]')"

        if [[ "${XRACK_WLAN_COUNTRY}" =~ ^[A-Z]{2}$ ]]; then
            break
        fi

        echo "$(L "Ungültiger Ländercode (genau 2 Buchstaben) - bitte erneut eingeben." "Invalid country code (exactly 2 letters) - please try again.")"
        XRACK_WLAN_COUNTRY=""
    done

    if [ -z "${XRACK_WLAN_COUNTRY}" ]; then
        return 0
    fi

    #
    # Denselben Weg gehen wie spaeter das Einstellungen-Menue: ein
    # Skript, eine Stelle. Sonst setzt der Installer die Region anders
    # als die Oberflaeche, und Unterschiede faellt niemandem auf,
    # bevor etwas nicht funktioniert.
    #
    # Ueber bash aufgerufen, weil das chmod erst spaeter kommt
    # (configure_sudoers) - aus einem entpackten Archiv haette die
    # Datei hier sonst womoeglich kein Ausfuehrungsrecht.
    sudo bash "${INSTALL_DIR}/scripts/xrack-wifi-country.sh" \
        "${XRACK_WLAN_COUNTRY}" || true
}

#
# Teil 2: eigener Access Point.
#
# Die eigentliche Einrichtung macht scripts/xrack-ap-setup.sh -
# dasselbe Skript, das XRack spaeter aus dem Einstellungen-Menue
# heraus aufruft. So gibt es nur einen Weg, einen Access Point
# aufzusetzen, und der ist an beiden Stellen derselbe.
#
configure_access_point() {

    AP_IFACE="$("${INSTALL_DIR}/scripts/xrack-wifi-iface.sh" ap)"

    if [ -z "${AP_IFACE}" ]; then
        echo ""
        echo "$(L "Kein zweites WLAN-Gerät gefunden - für einen Access Point wird ein USB-WLAN-Stick gebraucht." "No second Wi-Fi device found - an access point needs a USB Wi-Fi adapter.")"
        echo "$(L "Der Stick lässt sich jederzeit nachrüsten; der Access Point wird dann im Einstellungen-Menü eingerichtet." "You can add the adapter at any time; the access point is then set up in the settings menu.")"
        return 0
    fi

    frage_wlan_land

    echo ""
    read -r -p "$(L "Name des Access Points (Standard: XRack): " "Access point name (default: XRack): ")" AP_SSID_INPUT || true
    AP_SSID="${AP_SSID_INPUT:-XRack}"

    read_confirmed_secret "$(L "Passwort für den Access Point (mind. 8 Zeichen)" "Access point password (min. 8 characters)")" 8 AP_PASSWORD

    if [ "${#AP_PASSWORD}" -lt 8 ]; then
        echo "$(L "Passwort fehlt/zu kurz (mind. 8 Zeichen) - Access Point übersprungen." "Password missing/too short (min. 8 characters) - access point skipped.")"
        return 0
    fi

    echo ""
    echo "$(L "XRack: Access Point '${AP_SSID}' wird auf ${AP_IFACE} eingerichtet..." "XRack: Setting up access point '${AP_SSID}' on ${AP_IFACE}...")"

    if sudo "${INSTALL_DIR}/scripts/xrack-ap-setup.sh" \
        "${AP_SSID}" "${AP_PASSWORD}" "${XRACK_WLAN_COUNTRY}"; then

        XRACK_WLAN_AP_SSID="${AP_SSID}"
    else
        echo "$(L "Warnung: Access Point konnte nicht eingerichtet werden." "Warning: could not set up the access point.")"
    fi
}

#
# Das Profil fuer "Konsole aus dem Heimnetz erreichbar machen".
#
# Feste eigene Adressrange statt NetworkManager die Wahl zu lassen:
# Sonst kann sich das Subnetz je nach Reihenfolge anderer
# "shared"-Verbindungen zwischen 10.42.0.0/24 und 10.42.1.0/24
# verschieben, und die Portweiterleitung
# (scripts/xrack-port-forward.sh) zeigt auf eine veraltete
# Konsolen-IP.
#
# Angelegt, aber nicht aktiviert - eingeschaltet wird es im
# Einstellungen-Menue.
#
setup_wired_profile() {

    #
    # Das Standardprofil fuer die Netzwerkbuchse: ganz normaler
    # DHCP-Client. Das ist Betriebsart 1 aus der Erklaerung oben -
    # XRack und Mischpult haengen zusammen an einem Router.
    #
    # Warum das sein MUSS, und zwar immer:
    #
    # NetworkManager erzeugt seine automatische Kabelverbindung nur,
    # solange fuer das Geraet gar kein Profil passt. Sobald XRack
    # welche anlegt (die Bridge und die Freigabe, beide bewusst mit
    # "autoconnect no"), hoert das auf - und dann bringt niemand mehr
    # die Buchse hoch. Ein frisch aufgesetzter Pi war danach per
    # Kabel nicht mehr erreichbar und tauchte auch im Router nicht
    # mehr auf. Genau das ist passiert.
    #
    # Deshalb legt XRack die normale Kabelverbindung selbst an, mit
    # "autoconnect yes". Die Umschalt-Skripte legen sie beim
    # Umschalten still und holen sie beim Zurueckschalten wieder.
    #
    if ! nmcli -t -f NAME connection show | grep -qx "XRack-Wired-eth0"; then

        #
        # "dhcp-send-hostname yes" ist ohnehin die Vorgabe, steht hier
        # aber ausdruecklich: Nur so lernt der Router den Namen und
        # kann ihn selbst aufloesen (bei einer FRITZ!Box etwa als
        # "xrack" bzw. "xrack.fritz.box"). Das ist der zweite Weg zum
        # Geraet, unabhaengig von ".local" - und der einzige, der auch
        # ohne mDNS auf dem anfragenden Geraet funktioniert.
        #
        sudo nmcli connection add type ethernet ifname eth0 con-name "XRack-Wired-eth0" \
            ipv4.method auto \
            ipv4.dhcp-send-hostname yes \
            connection.autoconnect yes >/dev/null || return 1
    fi

    return 0
}

setup_share_profile() {

    sudo nmcli connection delete "XRack-Share-eth0" >/dev/null 2>&1 || true

    sudo nmcli connection add type ethernet ifname eth0 con-name "XRack-Share-eth0" \
        ipv4.method shared ipv4.addresses 10.77.0.1/24 \
        connection.autoconnect no >/dev/null || return 1

    return 0
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
# Lichtsteuerung: DMX über OLA (Open Lighting Architecture).
#
# XRack erzeugt das DMX-Signal nicht selbst. Ein DMX-Bild muss alle
# 23 Millisekunden neu geschrieben werden, mit einer Pause ("Break")
# von mindestens 88 Mikrosekunden davor - harte Echtzeit. Im selben
# Python-Prozess, der ALSA-Audio liest und den Webserver bedient,
# wäre jede Aufnahme und jeder Seitenaufruf eine mögliche Ursache
# für sichtbares Flackern.
#
# Deshalb dasselbe Muster wie beim WLAN (hostapd) und bei Bluetooth
# (bluetoothd): Ein ausgereifter Systemdienst übernimmt den
# zeitkritischen Teil, XRack schickt ihm nur Kanalwerte (siehe
# core/dmx_control.py).
#
# Kein sudoers-Eintrag nötig: olad läuft unter eigenem Benutzer, das
# USB-Kabel wird über eine udev-Regel freigegeben, und XRack spricht
# den Dienst über HTTP auf localhost an.
#
# Alles hier ist bewusst nicht abbrechend. Fehlt das Paket oder
# klappt etwas nicht, läuft XRack ohne Licht weiter - Aufnahme und
# Wiedergabe dürfen davon nie betroffen sein.
#
configure_dmx() {

    echo "$(L "XRack: Lichtsteuerung (DMX über OLA) wird eingerichtet..." "XRack: Setting up lighting control (DMX via OLA)...")"

    #
    # In einem eigenen Schritt und nicht in der großen Paketliste:
    # Wäre "ola" dort nicht verfügbar, schlüge die Installation
    # aller Systempakete fehl - wegen des Lichts.
    #
    if ! sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ola >/dev/null 2>&1; then

        echo "$(L "Hinweis: Paket 'ola' nicht installierbar - Lichtsteuerung nicht verfügbar." "Note: package 'ola' could not be installed - lighting control unavailable.")"
        return 0
    fi

    #
    # Das USB-DMX-Kabel freigeben.
    #
    # Alle gängigen Kabel dieser Preisklasse hängen an einem
    # FTDI-Chip (FT232R und Verwandte). Das ola-Paket bringt eigene
    # udev-Regeln mit und steckt seinen Benutzer in die Gruppen
    # dialout und plugdev; diese Regel hier ist die Rückversicherung
    # für Nachbauten, die dort nicht aufgeführt sind.
    #
    sudo tee /etc/udev/rules.d/99-xrack-dmx.rules > /dev/null <<'EOF'
SUBSYSTEM=="usb", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", GROUP="plugdev", MODE="0660"
SUBSYSTEM=="usb", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6014", GROUP="plugdev", MODE="0660"
SUBSYSTEM=="usb", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6015", GROUP="plugdev", MODE="0660"
EOF

    sudo udevadm control --reload-rules
    sudo udevadm trigger --subsystem-match=usb >/dev/null 2>&1 || true

    #
    # Wie heißt der Dienst? Das Debian-Paket hat lange nur ein
    # SysV-Startskript mitgebracht und erst seit Anfang 2026 eine
    # systemd-Unit. Je nach Stand des Betriebssystems heißt sie
    # "olad" oder "ola" - deshalb nachsehen statt raten.
    #
    DMX_UNIT=""

    for kandidat in olad.service ola.service; do

        if systemctl list-unit-files "${kandidat}" 2>/dev/null | grep -q "^${kandidat}"; then
            DMX_UNIT="${kandidat}"
            break
        fi
    done

    if [ -z "${DMX_UNIT}" ]; then
        echo "$(L "Hinweis: OLA-Dienst nicht gefunden - Licht bleibt aus, XRack läuft normal weiter." "Note: OLA service not found - lighting stays off, XRack runs normally.")"
        return 0
    fi

    sudo systemctl enable "${DMX_UNIT}" >/dev/null 2>&1 || true
    sudo systemctl start "${DMX_UNIT}" >/dev/null 2>&1 || true

    #
    # Wo liegen die Plugin-Einstellungen? Auch das ist je nach
    # Paketstand verschieden. Beim ersten Start legt olad die
    # Dateien selbst an, deshalb wird danach noch einmal gesucht.
    #
    DMX_CONF_DIR=""

    for versuch in 1 2; do

        for kandidat in /etc/ola /var/lib/ola/conf "$(getent passwd olad 2>/dev/null | cut -d: -f6)/.ola"; do

            if [ -n "${kandidat}" ] && [ -d "${kandidat}" ]; then
                DMX_CONF_DIR="${kandidat}"
                break
            fi
        done

        [ -n "${DMX_CONF_DIR}" ] && break

        sleep 2
    done

    if [ -z "${DMX_CONF_DIR}" ]; then
        echo "$(L "Hinweis: OLA-Konfiguration nicht gefunden - das DMX-Plugin muss von Hand aktiviert werden." "Note: OLA configuration not found - the DMX plugin has to be enabled manually.")"
        return 0
    fi

    #
    # Genau ein Plugin darf sich das Kabel greifen.
    #
    #   ftdidmx    - für "dumme" FTDI-Kabel ohne eigenen Prozessor,
    #                bei denen der Rechner das Timing macht. Das ist
    #                unser Fall (Open DMX USB und Nachbauten).
    #   usbserial  - für Kabel MIT eigenem Prozessor (Enttec USB Pro).
    #   opendmx    - dasselbe wie ftdidmx, aber über ein eigenes
    #                Kernelmodul.
    #
    # Alle drei erkennen dieselbe Hardware. Bleiben mehrere aktiv,
    # streiten sie sich darum, wer das Kabel bekommt - und das
    # Ergebnis hängt davon ab, wer zuerst da war.
    #
    ola_plugin_schalten "${DMX_CONF_DIR}/ola-ftdidmx.conf"   true
    ola_plugin_schalten "${DMX_CONF_DIR}/ola-usbserial.conf" false
    ola_plugin_schalten "${DMX_CONF_DIR}/ola-opendmx.conf"   false

    restrict_ola_to_loopback "${DMX_UNIT}"

    sudo systemctl restart "${DMX_UNIT}" >/dev/null 2>&1 || true
}

#
# Eine Plugin-Einstellung in einer OLA-Konfigurationsdatei setzen.
#
# Die Dateien gehören dem olad-Benutzer, deshalb läuft alles über
# sudo und der Besitzer wird danach wiederhergestellt - sonst könnte
# olad seine eigene Konfiguration beim nächsten Start nicht mehr
# schreiben.
#
ola_plugin_schalten() {

    datei="$1"
    wert="$2"

    if sudo test -f "${datei}"; then

        sudo sed -i "s/^[[:space:]]*enabled[[:space:]]*=.*/enabled = ${wert}/" "${datei}"

        if ! sudo grep -q "^enabled" "${datei}"; then
            echo "enabled = ${wert}" | sudo tee -a "${datei}" > /dev/null
        fi

    else
        echo "enabled = ${wert}" | sudo tee "${datei}" > /dev/null
    fi

    sudo chown olad:olad "${datei}" 2>/dev/null || true
}

#
# Die Weboberfläche von OLA auf localhost beschränken.
#
# olad bringt eine eigene, ungeschützte Weboberfläche mit (Port
# 9090) - über sie spricht XRack den Dienst an. Ohne Einschränkung
# wäre sie aber auch aus dem ganzen Netzwerk erreichbar: eine
# zweite Oberfläche neben XRacks eigener, ohne PIN, mit der jeder
# das Licht übernehmen könnte.
#
# "-i 127.0.0.1" bindet sie an die Loopback-Adresse. Die vorhandene
# Startzeile wird dafür ausgelesen und ergänzt, statt sie neu zu
# erfinden - je nach Paketstand steht dort Verschiedenes.
#
restrict_ola_to_loopback() {

    unit="$1"

    unit_datei="$(systemctl show -p FragmentPath --value "${unit}" 2>/dev/null)"

    if [ -z "${unit_datei}" ] || [ ! -f "${unit_datei}" ]; then
        echo "$(L "Hinweis: OLA-Startzeile nicht gefunden - die OLA-Weboberfläche (Port 9090) bleibt im Netzwerk erreichbar." "Note: OLA start command not found - the OLA web interface (port 9090) stays reachable on the network.")"
        return 0
    fi

    start_zeile="$(grep -m1 '^ExecStart=' "${unit_datei}" | sed 's/^ExecStart=//')"

    if [ -z "${start_zeile}" ]; then
        echo "$(L "Hinweis: OLA-Startzeile nicht lesbar - die OLA-Weboberfläche (Port 9090) bleibt im Netzwerk erreichbar." "Note: OLA start command unreadable - the OLA web interface (port 9090) stays reachable on the network.")"
        return 0
    fi

    #
    # Steht die Bindung schon drin, nichts tun - sonst stünde sie
    # nach einem zweiten Installationslauf doppelt da.
    #
    case "${start_zeile}" in
        *"-i 127.0.0.1"*) return 0 ;;
    esac

    #
    # Überschreibbar, damit der Test das prüfen kann, ohne an
    # /etc zu rühren - wie XRACK_HOSTAPD_CONF anderswo.
    #
    systemd_dir="${XRACK_SYSTEMD_DIR:-/etc/systemd/system}"

    sudo mkdir -p "${systemd_dir}/${unit}.d"

    sudo tee "${systemd_dir}/${unit}.d/xrack.conf" > /dev/null <<EOF
[Service]
ExecStart=
ExecStart=${start_zeile} -i 127.0.0.1
EOF

    sudo systemctl daemon-reload
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
        "${INSTALL_DIR}/scripts/xrack-ap-info.sh" \
        "${INSTALL_DIR}/scripts/xrack-bridge-toggle.sh" \
        "${INSTALL_DIR}/scripts/xrack-share-toggle.sh" \
        "${INSTALL_DIR}/scripts/xrack-dhcp-lease.sh" \
        "${INSTALL_DIR}/scripts/xrack-link-bounce.sh" \
        "${INSTALL_DIR}/scripts/xrack-bridge-ensure.sh" \
        "${INSTALL_DIR}/scripts/xrack-wired-restore.sh" \
        "${INSTALL_DIR}/scripts/xrack-wifi-iface.sh" \
        "${INSTALL_DIR}/scripts/xrack-wifi-country.sh" \
        "${INSTALL_DIR}/scripts/xrack-wifi-bind.sh" \
        "${INSTALL_DIR}/scripts/xrack-ap-setup.sh" \
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
${INSTALL_DIR}/scripts/xrack-ap-info.sh, \
${INSTALL_DIR}/scripts/xrack-bridge-toggle.sh *, \
${INSTALL_DIR}/scripts/xrack-share-toggle.sh *, \
${INSTALL_DIR}/scripts/xrack-dhcp-lease.sh *, \
${INSTALL_DIR}/scripts/xrack-link-bounce.sh *, \
${INSTALL_DIR}/scripts/xrack-port-forward.sh *, \
${INSTALL_DIR}/scripts/xrack-bt-power.sh *, \
${INSTALL_DIR}/scripts/xrack-bt-pair.sh, \
${INSTALL_DIR}/scripts/xrack-bt-forget.sh *, \
${INSTALL_DIR}/scripts/xrack-bt-disconnect.sh *, \
${INSTALL_DIR}/scripts/xrack-update.py *, \
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
    echo "$(L "Webinterface:             https://<ip-des-pi>:${XRACK_PORT}" "Web interface:            https://<pi-ip>:${XRACK_PORT}")"
    echo "$(L "                          (oft auch: https://${XRACK_HOSTNAME}.local:${XRACK_PORT} - das können" "                          (often also: https://${XRACK_HOSTNAME}.local:${XRACK_PORT} - but not")"
    echo "$(L "                          aber nicht alle Router und Geräte auflösen)" "                          every router and device can resolve that)")"
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

    if [ -n "${XRACK_WLAN_AP_SSID}" ]; then
        echo "$(L "Access-Point-Netz:        br0, 10.42.0.1 (DHCP von XRack)" "Access point network:     br0, 10.42.0.1 (DHCP served by XRack)")"
    fi

    if [ "${XRACK_WLAN_BRIDGE}" = "ja" ]; then
        echo "$(L "Konsole über den Access Point: im Einstellungen-Menü zuschaltbar, aktuell aus" "Console via access point:     can be enabled in the settings menu, currently off")"
    fi

    if [ "${XRACK_WLAN_SHARE_READY}" = "ja" ]; then
        echo "$(L "Konsole aus dem Heimnetz:     im Einstellungen-Menü zuschaltbar, aktuell aus" "Console from home network:    can be enabled in the settings menu, currently off")"
    fi

    if [ -z "${XRACK_WLAN_AP_SSID}" ]; then
        echo ""
        echo "$(L "Ein Access Point lässt sich jederzeit im Einstellungen-Menü nachrüsten -" "An access point can be added at any time from the settings menu -")"
        echo "$(L "install.sh muss dafür nicht noch einmal laufen." "install.sh does not need to run again for that.")"
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

    echo ""
    echo "$(L "Der Raspberry Pi sollte jetzt neu gestartet werden - erst danach" "The Raspberry Pi should be restarted now - only then does")"
    echo "$(L "zeigt sich, ob alles auch von selbst wieder hochkommt." "everything come back up on its own, as it should.")"

    if [ ! -t 0 ]; then
        echo "$(L "Bitte manuell neu starten, sobald es passt: sudo reboot" "Please restart manually whenever it suits you: sudo reboot")"
        return 0
    fi

    echo ""
    read -r -p "$(L "Jetzt neu starten? [J/n]: " "Restart now? [Y/n]: ")" XRACK_REBOOT_NOW || true

    if [ "$(lower "${XRACK_REBOOT_NOW}")" = "n" ]; then
        echo "$(L "Bitte bei Gelegenheit manuell neu starten: sudo reboot" "Please restart manually when convenient: sudo reboot")"
        return 0
    fi

    echo "$(L "XRack: Neustart..." "XRack: Restarting...")"
    sudo reboot
}

#
# Ablauf
#

#
# Wird install.sh nur eingelesen statt ausgefuehrt, hier aufhoeren:
# Dann stehen die Funktionen zur Verfuegung, ohne dass etwas
# installiert wird. Genau das macht test_wlan_setup.py, um
# die WLAN-Einrichtung durchzuspielen - ohne diesen Ausstieg wuerde
# der Test anfangen, Pakete zu installieren.
#
if [ -n "${XRACK_INSTALL_SOURCE_ONLY}" ]; then
    return 0 2>/dev/null || exit 0
fi

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
configure_dmx
configure_sudoers
configure_systemd_service
print_summary
offer_reboot_for_bridge
