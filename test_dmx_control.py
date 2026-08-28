#!/usr/bin/env python3
"""
Prüft core/dmx_control.py - die Anbindung an den Lichtdienst olad.

Für den Austausch läuft ein "Attrappen-Dienst": ein HTTP-Server auf
localhost, der sich wie olad verhält und mitschreibt, was ankommt.
Damit lässt sich alles durchspielen, ohne dass ein DMX-Kabel oder
eine Lampe in der Nähe sein muss - genau wie beim Attrappen-Pult in
test_console_control.py.

Was der Test NICHT beantworten kann: ob olad die geschickten Werte
tatsächlich auf das Kabel bringt und ob die Lampe angeht. Das
entscheidet sich am Gerät.
"""

import os
import subprocess
import tempfile
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from core.dmx_control import DmxControl


# ====================================================================
# Der Attrappen-Dienst
# ====================================================================

class OladAttrappe(BaseHTTPRequestHandler):
    """Nimmt POSTs auf /set_dmx entgegen und merkt sich den Inhalt."""

    empfangen = []
    antwort_code = 200

    def do_POST(self):

        laenge = int(self.headers.get("Content-Length", 0))
        koerper = self.rfile.read(laenge).decode("ascii")

        OladAttrappe.empfangen.append((self.path, koerper))

        self.send_response(OladAttrappe.antwort_code)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_GET(self):

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OLA")

    def log_message(self, *args):
        """Stille - sonst rauscht der Testlauf voll."""


def dienst_starten() -> tuple[HTTPServer, str]:
    """Startet die Attrappe auf einem freien Port."""

    server = HTTPServer(("127.0.0.1", 0), OladAttrappe)

    threading.Thread(target=server.serve_forever, daemon=True).start()

    return server, f"http://127.0.0.1:{server.server_port}"


def letzte_werte() -> list[int]:
    """Die Kanalwerte aus dem zuletzt empfangenen Aufruf."""

    _, koerper = OladAttrappe.empfangen[-1]

    felder = urllib.parse.parse_qs(koerper)

    return [int(wert) for wert in felder["d"][0].split(",")]


# ====================================================================
# 1. Senden: kommt an, was gemeint war?
# ====================================================================

server, adresse = dienst_starten()

dmx = DmxControl(base_url=adresse)

assert dmx.send([0, 128, 255]) is True, "Senden an die Attrappe schlug fehl."

pfad, koerper = OladAttrappe.empfangen[-1]

assert pfad == "/set_dmx", f"Falscher Pfad angesprochen: {pfad}"

felder = urllib.parse.parse_qs(koerper)

assert felder["u"] == ["1"], f"Falsches Universum: {felder.get('u')}"
assert letzte_werte() == [0, 128, 255], letzte_werte()

print("OK: Kanalwerte kommen unverändert beim Dienst an")


# ====================================================================
# 2. Unsinnige Werte halten die Show nicht an
#
# Ein Rechenfehler in der Lichtberechnung darf höchstens eine Lampe
# falsch aussteuern - nicht die Ausgabe abwürgen.
# ====================================================================

assert dmx.send([-5, 300, 42]) is True, "Werte außerhalb 0-255 wurden abgewiesen."
assert letzte_werte() == [0, 255, 42], letzte_werte()

print("OK: Werte außerhalb 0-255 werden abgeschnitten, nicht abgewiesen")

#
# Mehr Werte als ein Universum Kanäle hat: Der Rest wird verworfen,
# der Aufruf gilt trotzdem als erfolgreich.
#
assert dmx.send([7] * 600) is True, "Zu lange Liste wurde abgewiesen."
assert len(letzte_werte()) == DmxControl.CHANNELS, len(letzte_werte())

print("OK: Mehr als 512 Kanäle werden gekappt statt abgelehnt")


# ====================================================================
# 3. Blackout
# ====================================================================

assert dmx.blackout() is True, "Blackout schlug fehl."

werte = letzte_werte()

assert len(werte) == DmxControl.CHANNELS, len(werte)
assert set(werte) == {0}, "Beim Blackout müssen alle Kanäle 0 sein."

print("OK: Blackout setzt alle 512 Kanäle auf 0")


# ====================================================================
# 4. Kein Proxy für localhost
#
# urllib nimmt sich sonst ungefragt http_proxy aus der Umgebung und
# schickt den Aufruf an 127.0.0.1 über einen Proxy, der ihn nie
# zustellen kann. Der Fehler wäre von außen kaum zu erkennen -
# deshalb hier festgehalten.
# ====================================================================

#
# no_proxy muss dabei weg. Steht dort - wie in vielen Umgebungen -
# schon 127.0.0.1 drin, umgeht urllib den Proxy von sich aus, und
# der Test ginge auch ohne die Vorkehrung im Code durch. Er würde
# dann nichts prüfen. (Genau das ist beim ersten Anlauf passiert:
# Die Gegenprobe mit entfernter Vorkehrung blieb grün.)
#
PROXY_VARIABLEN = ("http_proxy", "HTTP_PROXY", "no_proxy", "NO_PROXY")

vorher = {name: os.environ.get(name) for name in PROXY_VARIABLEN}

try:

    for name in PROXY_VARIABLEN:
        os.environ.pop(name, None)

    os.environ["http_proxy"] = "http://127.0.0.1:9"  # Port 9 verschluckt alles

    frisch = DmxControl(base_url=adresse)

    assert frisch.send([1, 2, 3]) is True, (
        "Mit gesetztem http_proxy ging der Aufruf an localhost verloren."
    )
    assert letzte_werte() == [1, 2, 3], letzte_werte()

    print("OK: Ein gesetzter http_proxy stört den Aufruf an localhost nicht")

finally:

    for name, wert in vorher.items():

        if wert is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = wert


# ====================================================================
# 5. Läuft der Dienst?
# ====================================================================

assert dmx.service_running is True, "Laufender Dienst wurde nicht erkannt."

print("OK: Ein laufender Dienst wird erkannt")

server.shutdown()
server.server_close()

#
# Und jetzt das, was im Betrieb wirklich zählt: Ist der Dienst weg,
# darf nichts fliegen. Licht darf Aufnahme und Wiedergabe nie
# stören - es bleibt dunkel, XRack läuft weiter.
#
tot = DmxControl(base_url=adresse)

assert tot.service_running is False, "Toter Dienst wurde als laufend gemeldet."
assert tot.send([255] * 10) is False, (
    "Senden an einen toten Dienst muss False liefern, nicht durchgehen."
)
assert tot.blackout() is False, "Blackout an einen toten Dienst muss False liefern."

print("OK: Ohne Dienst gibt es kein Licht - aber auch keinen Absturz")


# ====================================================================
# 6. Kabelerkennung über den Kernel
#
# Bewusst über /sys und nicht über olad: Der Kernel weiß es sicher,
# und die Antwort bleibt auch dann brauchbar, wenn der Dienst gerade
# nicht läuft - genau der Fall, in dem man wissen will, ob wenigstens
# das Kabel steckt.
# ====================================================================

def usb_baum(wurzel: Path, geraete: dict) -> Path:
    """Stellt /sys/bus/usb/devices nach. Name -> (Vendor, Produkt, Name)."""

    basis = wurzel / "sys" / "bus" / "usb" / "devices"
    basis.mkdir(parents=True, exist_ok=True)

    for kennung, (hersteller, produkt, name) in geraete.items():

        geraet = basis / kennung
        geraet.mkdir()
        (geraet / "idVendor").write_text(f"{hersteller}\n")
        (geraet / "idProduct").write_text(f"{produkt}\n")

        if name:
            (geraet / "product").write_text(f"{name}\n")

    return basis


with tempfile.TemporaryDirectory() as tmp:

    wurzel = Path(tmp)

    basis = usb_baum(wurzel, {
        "1-1":     ("0403", "6001", "FT232R USB UART"),
        "1-2":     ("1d6b", "0002", "xHCI Host Controller"),
        "usb1":    ("8087", "0024", "Irgendein Hub"),
    })

    #
    # Ein USB-Gerät ohne idVendor (etwa ein Interface-Unterordner)
    # darf die Suche nicht abbrechen.
    #
    (basis / "1-1:1.0").mkdir()

    dmx = DmxControl(base_url=adresse, usb_devices=basis)

    gefunden = dmx.adapters()

    assert len(gefunden) == 1, f"Erwartet genau ein FTDI-Gerät, gefunden: {gefunden}"
    assert gefunden[0]["device"] == "1-1", gefunden
    assert gefunden[0]["product_id"] == "6001", gefunden
    assert gefunden[0]["name"] == "FT232R USB UART", gefunden
    assert dmx.adapter_present is True

    print("OK: Das FTDI-Kabel wird erkannt, anderes USB-Zeug nicht")


with tempfile.TemporaryDirectory() as tmp:

    basis = usb_baum(Path(tmp), {
        "1-2": ("1d6b", "0002", "xHCI Host Controller"),
    })

    dmx = DmxControl(base_url=adresse, usb_devices=basis)

    assert dmx.adapters() == [], dmx.adapters()
    assert dmx.adapter_present is False

    print("OK: Ohne FTDI-Gerät wird nichts behauptet")


#
# Und wenn es den /sys-Zweig gar nicht gibt - etwa weil der Test auf
# einem anderen Betriebssystem läuft - darf das nicht fliegen.
#
dmx = DmxControl(base_url=adresse, usb_devices=Path("/gibt/es/nicht"))

assert dmx.adapters() == [], "Ein fehlender /sys-Zweig muss eine leere Liste liefern."

print("OK: Ein fehlender /sys-Zweig kippt die Erkennung nicht")


# ====================================================================
# 7. Der Statusbericht für die Oberfläche
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    basis = usb_baum(Path(tmp), {"1-1": ("0403", "6001", "DMX-Kabel")})

    server, adresse = dienst_starten()

    dmx = DmxControl(base_url=adresse, usb_devices=basis)

    stand = dmx.status()

    assert stand["service_running"] is True, stand
    assert stand["adapter_present"] is True, stand
    assert stand["universe"] == 1, stand
    assert stand["channels"] == 512, stand
    assert len(stand["adapters"]) == 1, stand

    print("OK: Der Statusbericht nennt Dienst, Kabel und Universum")

    server.shutdown()
    server.server_close()


# ====================================================================
# 8. Die Einrichtung in install.sh
#
# Zwei Hilfsfunktionen dort haben echte Logik, und beide scheitern
# leise, wenn sie schiefgehen: Das Plugin bliebe stumm aus, oder
# OLAs ungeschützte Weboberfläche bliebe im Netzwerk erreichbar.
# Deshalb werden sie hier mit nachgestellten Werkzeugen durchgespielt
# - install.sh wird dafür nur eingelesen, nicht ausgeführt
# (XRACK_INSTALL_SOURCE_ONLY), wie in test_wlan_setup.py.
# ====================================================================

INSTALL = Path(__file__).resolve().parent / "install.sh"

FAKE_SUDO = "#!/bin/sh\n# sudo wegdenken: ausfuehren, was dahinter steht.\nexec \"$@\"\n"

#
# Der Test laeuft nicht als root - Besitzer setzen geht nicht und ist
# hier auch nicht das, was geprueft wird.
#
FAKE_CHOWN = "#!/bin/sh\nexit 0\n"


def werkzeuge(ordner: Path, unit_datei: Path) -> dict:
    """Legt die nachgestellten Werkzeuge an und liefert die Umgebung."""

    binordner = ordner / "bin"
    binordner.mkdir(parents=True, exist_ok=True)

    fake_systemctl = (
        "#!/bin/sh\n"
        'if [ "$1" = "show" ]; then\n'
        f'    echo "{unit_datei}"\n'
        "    exit 0\n"
        "fi\n"
        "exit 0\n"
    )

    for name, inhalt in (
        ("sudo", FAKE_SUDO),
        ("chown", FAKE_CHOWN),
        ("systemctl", fake_systemctl),
    ):
        datei = binordner / name
        datei.write_text(inhalt, encoding="utf-8")
        datei.chmod(0o755)

    umgebung = dict(os.environ)
    umgebung["PATH"] = f"{binordner}:{os.environ['PATH']}"
    umgebung["XRACK_SYSTEMD_DIR"] = str(ordner / "systemd")
    umgebung["XRACK_LANGUAGE"] = "de"

    return umgebung


def install_funktion(ordner: Path, umgebung: dict, aufrufe: list[str]) -> str:
    """Liest install.sh ein und ruft darin Funktionen auf."""

    skript = ordner / "lauf.sh"
    skript.write_text(
        "\n".join([
            "export XRACK_INSTALL_SOURCE_ONLY=1",
            f"source {INSTALL}",
            *aufrufe,
        ]),
        encoding="utf-8",
    )

    ergebnis = subprocess.run(
        ["bash", str(skript)],
        capture_output=True, text=True, env=umgebung, timeout=60,
    )

    assert ergebnis.returncode == 0, (ergebnis.returncode, ergebnis.stderr)

    return ergebnis.stdout


# --- Plugin an- und abschalten --------------------------------------

with tempfile.TemporaryDirectory() as tmp:

    ordner = Path(tmp)
    umgebung = werkzeuge(ordner, ordner / "olad.service")

    # a) Datei da, Plugin steht auf aus -> muss an sein, Rest bleibt.
    vorhanden = ordner / "ola-ftdidmx.conf"
    vorhanden.write_text("enabled = false\nfrequency = 30\n", encoding="utf-8")

    # b) Datei da, aber ohne Zeile "enabled" -> muss ergaenzt werden.
    ohne = ordner / "ola-usbserial.conf"
    ohne.write_text("device_dir = /dev\n", encoding="utf-8")

    # c) Datei gibt es gar nicht -> muss angelegt werden.
    fehlt = ordner / "ola-opendmx.conf"

    install_funktion(ordner, umgebung, [
        f'ola_plugin_schalten "{vorhanden}" true',
        f'ola_plugin_schalten "{ohne}" false',
        f'ola_plugin_schalten "{fehlt}" false',
    ])

    zeilen = vorhanden.read_text(encoding="utf-8").splitlines()

    assert "enabled = true" in zeilen, zeilen
    assert "enabled = false" not in zeilen, zeilen
    assert "frequency = 30" in zeilen, (
        "Beim Umschalten ist der Rest der Datei verlorengegangen: " + str(zeilen)
    )

    print("OK: Ein vorhandenes Plugin wird umgeschaltet, ohne den Rest anzufassen")

    zeilen = ohne.read_text(encoding="utf-8").splitlines()

    assert "enabled = false" in zeilen, zeilen
    assert "device_dir = /dev" in zeilen, zeilen

    print("OK: Fehlt die Zeile 'enabled', wird sie ergänzt")

    assert fehlt.exists(), "Die fehlende Konfigurationsdatei wurde nicht angelegt."
    assert "enabled = false" in fehlt.read_text(encoding="utf-8"), fehlt.read_text()

    print("OK: Eine noch nicht vorhandene Konfigurationsdatei wird angelegt")


# --- OLAs Weboberfläche auf localhost festnageln --------------------

with tempfile.TemporaryDirectory() as tmp:

    ordner = Path(tmp)

    unit = ordner / "olad.service"
    unit.write_text(
        "[Unit]\n"
        "Description=OLA Daemon\n"
        "\n"
        "[Service]\n"
        "ExecStart=/usr/bin/olad --config-dir /etc/ola\n",
        encoding="utf-8",
    )

    umgebung = werkzeuge(ordner, unit)

    install_funktion(ordner, umgebung, ['restrict_ola_to_loopback "olad.service"'])

    dropin = ordner / "systemd" / "olad.service.d" / "xrack.conf"

    assert dropin.exists(), "Es wurde keine Ergänzung zur Unit geschrieben."

    inhalt = dropin.read_text(encoding="utf-8")

    #
    # Die leere ExecStart-Zeile muss davorstehen, sonst haengt systemd
    # den neuen Befehl an den alten an, statt ihn zu ersetzen - und
    # olad liefe zweimal.
    #
    assert "ExecStart=\n" in inhalt, (
        "Ohne leere ExecStart-Zeile ersetzt systemd den Startbefehl nicht:\n"
        + inhalt
    )
    assert "ExecStart=/usr/bin/olad --config-dir /etc/ola -i 127.0.0.1" in inhalt, inhalt

    print("OK: Die OLA-Weboberfläche wird an 127.0.0.1 gebunden")

    #
    # Ein zweiter Installationslauf darf die Bindung nicht doppelt
    # eintragen.
    #
    unit.write_text(
        "[Service]\nExecStart=/usr/bin/olad --config-dir /etc/ola -i 127.0.0.1\n",
        encoding="utf-8",
    )

    dropin.unlink()

    install_funktion(ordner, umgebung, ['restrict_ola_to_loopback "olad.service"'])

    assert not dropin.exists(), (
        "Bei bereits gesetzter Bindung darf keine zweite Ergänzung entstehen."
    )

    print("OK: Ein zweiter Lauf trägt die Bindung nicht doppelt ein")


with tempfile.TemporaryDirectory() as tmp:

    ordner = Path(tmp)

    #
    # Unit ohne ExecStart: Dann wird nichts erfunden - aber es muss
    # dastehen, dass die Oberflaeche offen bleibt. Stillschweigen
    # waere hier das Schlimmste.
    #
    unit = ordner / "olad.service"
    unit.write_text("[Unit]\nDescription=OLA Daemon\n", encoding="utf-8")

    umgebung = werkzeuge(ordner, unit)

    ausgabe = install_funktion(
        ordner, umgebung, ['restrict_ola_to_loopback "olad.service"']
    )

    assert not (ordner / "systemd").exists(), (
        "Ohne lesbare Startzeile darf keine Ergänzung geschrieben werden."
    )
    assert "9090" in ausgabe, (
        "Der Hinweis auf die offene OLA-Weboberfläche fehlt:\n" + ausgabe
    )

    print("OK: Ohne lesbare Startzeile wird nichts erfunden, sondern gewarnt")


print("Alle DMX-Tests erfolgreich.")
