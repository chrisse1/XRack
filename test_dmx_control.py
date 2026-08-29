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

    #
    # Der nachgestellte systemctl schreibt mit, was mit ihm gemacht
    # wird.
    #
    # Ohne dieses Mitschreiben konnte ein fehlendes "enable" gar nicht
    # auffallen - und genau daran lag es am Geraet: Die eigene Unit
    # wurde geschrieben und gestartet, aber nie eingeschaltet.
    #
    protokoll = ordner / "systemctl.log"

    fake_systemctl = (
        "#!/bin/sh\n"
        f'echo "$@" >> "{protokoll}"\n'
        'if [ "$1" = "show" ]; then\n'
        f'    echo "{unit_datei}"\n'
        "    exit 0\n"
        "fi\n"
        "exit 0\n"
    )

    #
    # "command -v olad" muss etwas finden, und "getent passwd olad"
    # muss den Dienstbenutzer melden - beides entscheidet, was in die
    # eigene Unit geschrieben wird.
    #
    FAKE_OLAD = "#!/bin/sh\nexit 0\n"
    FAKE_GETENT = (
        "#!/bin/sh\n"
        'if [ "$1" = "passwd" ] && [ "$2" = "olad" ]; then\n'
        "    echo 'olad:x:102:65534::/var/lib/ola:/usr/sbin/nologin'\n"
        "    exit 0\n"
        "fi\n"
        "exit 2\n"
    )

    #
    # dpkg-query und apt-get. Beide schreiben mit, und beide lassen
    # sich ueber Dateien steuern:
    #
    #   paket_da   - existiert sie, gilt ola als installiert
    #   apt_bricht - existiert sie, scheitert apt-get
    #   apt_legt   - existiert sie, legt apt-get "paket_da" an
    #
    # Ueber Dateien und nicht ueber Umgebungsvariablen, weil sich der
    # Zustand so MITTEN im Lauf aendern kann - genau das braucht der
    # Fall "erst nicht da, nach dem apt-Aufruf da".
    #
    apt_log = ordner / "apt.log"

    fake_dpkg = (
        "#!/bin/sh\n"
        f'echo "$@" >> "{ordner}/dpkg.log"\n'
        f'if [ -f "{ordner}/paket_da" ]; then\n'
        "    echo 'install ok installed'\n"
        "    exit 0\n"
        "fi\n"
        "echo 'unknown ok not-installed'\n"
        "exit 1\n"
    )

    fake_apt = (
        "#!/bin/sh\n"
        f'echo "$@" >> "{apt_log}"\n'
        f'if [ -f "{ordner}/apt_legt" ]; then touch "{ordner}/paket_da"; fi\n'
        f'if [ -f "{ordner}/apt_bricht" ]; then\n'
        "    echo 'E: Unable to locate package ola' >&2\n"
        "    exit 100\n"
        "fi\n"
        "exit 0\n"
    )

    for name, inhalt in (
        ("sudo", FAKE_SUDO),
        ("chown", FAKE_CHOWN),
        ("systemctl", fake_systemctl),
        ("olad", FAKE_OLAD),
        ("getent", FAKE_GETENT),
        ("dpkg-query", fake_dpkg),
        ("apt-get", fake_apt),
    ):
        datei = binordner / name
        datei.write_text(inhalt, encoding="utf-8")
        datei.chmod(0o755)

    umgebung = dict(os.environ)
    umgebung["PATH"] = f"{binordner}:{os.environ['PATH']}"
    umgebung["XRACK_SYSTEMD_DIR"] = str(ordner / "systemd")
    umgebung["XRACK_LANGUAGE"] = "de"
    umgebung["XRACK_SYSTEMCTL_LOG"] = str(protokoll)
    umgebung["XRACK_APT_LOG"] = str(apt_log)

    return umgebung


def apt_aufrufe(umgebung: dict) -> list[str]:
    """Womit apt-get aufgerufen wurde, in der Reihenfolge."""

    protokoll = Path(umgebung["XRACK_APT_LOG"])

    if not protokoll.exists():
        return []

    return protokoll.read_text(encoding="utf-8").splitlines()


def systemctl_aufrufe(umgebung: dict) -> list[str]:
    """Was mit systemctl gemacht wurde, in der Reihenfolge."""

    protokoll = Path(umgebung["XRACK_SYSTEMCTL_LOG"])

    if not protokoll.exists():
        return []

    return protokoll.read_text(encoding="utf-8").splitlines()


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


# --- Der SysV-Fall: eigene Unit statt wirkungsloser Ergaenzung ------
#
# Am Geraet kam heraus: Dort gibt es keine echte systemd-Unit,
# sondern ein altes Startskript, das systemd nur einpackt. Die
# Ergaenzung haengte "-i 127.0.0.1" an den Aufruf des Startskripts,
# das die Option ignoriert - eingerichtet sah es aus, gewirkt hat es
# nicht. Deshalb in diesem Fall eine eigene Unit.

with tempfile.TemporaryDirectory() as tmp:

    ordner = Path(tmp)

    #
    # systemd legt aus einem SysV-Skript erzeugte Units unter
    # .../generator.late/ ab - daran wird der Fall erkannt.
    #
    erzeugt = ordner / "generator.late"
    erzeugt.mkdir()

    unit = erzeugt / "olad.service"
    unit.write_text(
        "[Unit]\n"
        "Description=LSB: OLA daemon\n"
        "\n"
        "[Service]\n"
        "ExecStart=/etc/init.d/olad start\n",
        encoding="utf-8",
    )

    umgebung = werkzeuge(ordner, unit)

    #
    # Eine alte, wirkungslose Ergaenzung aus einem frueheren Lauf.
    # Die muss verschwinden: Sonst setzte sie ExecStart der eigenen
    # Unit wieder auf den Aufruf des Startskripts zurueck.
    #
    alte_ergaenzung = ordner / "systemd" / "olad.service.d" / "xrack.conf"
    alte_ergaenzung.parent.mkdir(parents=True)
    alte_ergaenzung.write_text(
        "[Service]\nExecStart=\nExecStart=/etc/init.d/olad start -i 127.0.0.1\n",
        encoding="utf-8",
    )

    install_funktion(ordner, umgebung, [
        f'restrict_ola_to_loopback "olad.service" "{ordner}/ola"'
    ])

    eigene = ordner / "systemd" / "olad.service"

    assert eigene.exists(), "Es wurde keine eigene Unit geschrieben."

    inhalt = eigene.read_text(encoding="utf-8")

    assert inhalt.count("-i 127.0.0.1") == 1, inhalt
    assert f"--config-dir {ordner}/ola" in inhalt, inhalt
    assert "/olad --syslog" in inhalt, (
        "Die eigene Unit muss olad direkt starten, nicht das Startskript:\n"
        + inhalt
    )
    assert "/etc/init.d/olad" not in inhalt, (
        "Die eigene Unit darf nicht wieder das Startskript aufrufen:\n" + inhalt
    )
    assert "User=olad" in inhalt, inhalt

    assert not alte_ergaenzung.exists(), (
        "Die alte, wirkungslose Ergänzung wurde nicht entfernt - sie würde "
        "ExecStart der eigenen Unit wieder überschreiben."
    )

    print("OK: Beim SysV-Startskript entsteht eine eigene Unit, und die alte "
          "Ergänzung verschwindet")

    #
    # Ein zweiter Lauf darf nichts doppeln.
    #
    install_funktion(ordner, umgebung, [
        f'restrict_ola_to_loopback "olad.service" "{ordner}/ola"'
    ])

    assert eigene.read_text(encoding="utf-8").count("-i 127.0.0.1") == 1, (
        eigene.read_text(encoding="utf-8")
    )

    print("OK: Ein zweiter Lauf lässt die eigene Unit unverändert")


# --- Die Streithaehne muessen alle in der Abschaltliste stehen -------
#
# Das ist bewusst eine Pruefung am Quelltext und keine am Verhalten:
# configure_dmx laesst sich nicht durchspielen, ohne apt-get
# loszuschicken. Trotzdem gehoert die Zusicherung hierher, denn genau
# hier war der Fehler: stageprofi fehlte in der Liste, griff sich das
# Kabel im Sekundentakt, und es blieb dunkel - ohne dass irgendwo
# eine Fehlermeldung stand.

quelltext = INSTALL.read_text(encoding="utf-8")

zeile = [z for z in quelltext.splitlines() if "for streithahn in" in z]

assert len(zeile) == 1, f"Abschaltliste nicht eindeutig gefunden: {zeile}"

for plugin in ("usbserial", "opendmx", "stageprofi"):
    assert plugin in zeile[0], (
        f"'{plugin}' fehlt in der Abschaltliste - dieses Plugin greift sich "
        f"dasselbe Kabel wie ftdidmx: {zeile[0]}"
    )

assert "ola-ftdidmx.conf\" true" in quelltext, (
    "ftdidmx muss ausdrücklich eingeschaltet werden."
)

print("OK: Alle Plugins, die sich um das Kabel streiten, werden abgeschaltet")


# ====================================================================
# 9. Die eigene Unit muss auch eingeschaltet werden
#
# Am Geraet gefunden, nach einem Neustart des Raspberry:
#
#   olad.service - OLA-Dienst fuers Licht (von XRack eingerichtet)
#        Loaded: loaded (/etc/systemd/system/olad.service; disabled)
#        Active: inactive (dead)
#
# In configure_dmx wird zwar "enable" gerufen - aber fuer die Unit,
# die es zu DIESEM Zeitpunkt gab. Auf einem System mit SysV-Startskript
# ist das die von systemd erzeugte, und die Startverknuepfung entsteht
# ueber die Runlevel-Links des Init-Skripts. Die eigene Unit, die
# restrict_ola_to_loopback danach daneben schreibt, hat davon nichts.
#
# Heimtueckisch ist der Zeitpunkt: Bis zum naechsten Neustart laeuft
# alles, weil der alte Daemon noch laeuft. Der Fehler zeigt sich erst
# beim Hochfahren - also genau dann, wenn man ihn am wenigsten
# gebrauchen kann.
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    ordner = Path(tmp)

    #
    # Der SysV-Fall: Hier schreibt install.sh eine eigene Unit, und
    # genau hier fehlte das Einschalten.
    #
    erzeugt = ordner / "generator" / "olad.service"
    erzeugt.parent.mkdir(parents=True)
    erzeugt.write_text(
        "[Service]\nExecStart=/etc/init.d/olad start\n", encoding="utf-8"
    )

    umgebung = werkzeuge(ordner, erzeugt)

    install_funktion(
        ordner, umgebung,
        ['restrict_ola_to_loopback "olad.service" "/etc/ola"'],
    )

    assert (ordner / "systemd" / "olad.service").exists(), (
        "Es wurde keine eigene Unit geschrieben."
    )

    aufrufe = systemctl_aufrufe(umgebung)

    assert any("enable olad.service" in a for a in aufrufe), (
        "Die eigene Unit wurde geschrieben, aber nie eingeschaltet - nach "
        "einem Neustart bliebe das Licht tot. Aufrufe: " + str(aufrufe)
    )

    #
    # Und zwar NACH dem Neuladen: Vorher kennt systemd die Datei noch
    # gar nicht, und das Einschalten ginge ins Leere.
    #
    reload_stelle = next(
        i for i, a in enumerate(aufrufe) if a.startswith("daemon-reload")
    )
    enable_stelle = next(
        i for i, a in enumerate(aufrufe) if "enable olad.service" in a
    )

    assert enable_stelle > reload_stelle, (
        "Eingeschaltet wurde vor dem Neuladen - systemd kennt die neue "
        f"Unit da noch nicht. Aufrufe: {aufrufe}"
    )

    print("OK: Die eigene Unit wird nach dem Neuladen auch eingeschaltet")


with tempfile.TemporaryDirectory() as tmp:

    #
    # Und bei einer echten systemd-Unit ebenso. Dort ist es zwar ein
    # Nichts-Tun, weil configure_dmx sie schon eingeschaltet hat -
    # aber es darf nicht davon abhaengen, in welchem Zweig man landet.
    #
    ordner = Path(tmp)

    unit = ordner / "olad.service"
    unit.write_text(
        "[Service]\nExecStart=/usr/bin/olad --config-dir /etc/ola\n",
        encoding="utf-8",
    )

    umgebung = werkzeuge(ordner, unit)

    install_funktion(ordner, umgebung, ['restrict_ola_to_loopback "olad.service"'])

    assert any(
        "enable olad.service" in a for a in systemctl_aufrufe(umgebung)
    ), systemctl_aufrufe(umgebung)

    print("OK: Auch bei einer echten systemd-Unit wird eingeschaltet")


# ====================================================================
# 10. Die Paketpruefung darf nicht falsch anschlagen
#
# Am Geraet gemeldet, beim zweiten Lauf des Installers:
#
#   Hinweis: Paket 'ola' nicht installierbar - Lichtsteuerung nicht
#   verfuegbar.
#
# waehrend "sudo apt install ola" meldete, es sei laengst die neueste
# Version. Auf den Fehlschlag folgte ein return - uebersprungen wurden
# damit udev-Regel, Plugin-Einstellungen, die eigene Unit und der
# systemctl-enable-Aufruf, wegen dem der Installer ueberhaupt noch
# einmal lief.
#
# Ursache war "sudo VAR=wert apt-get ...": Ob sudo eine auf der
# Kommandozeile gesetzte Umgebungsvariable durchlaesst, haengt an der
# sudoers-Regel. Laesst sie es nicht, bricht sudo ab, BEVOR apt
# startet - und die Ausgabe war zusaetzlich verschluckt.
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    #
    # Der gemeldete Fall: Das Paket ist schon da.
    #
    ordner = Path(tmp)
    umgebung = werkzeuge(ordner, ordner / "olad.service")

    (ordner / "paket_da").touch()

    #
    # Damit apt, falls es doch gerufen wuerde, auch scheitern WUERDE -
    # so faellt ein ueberfluessiger Aufruf gleich doppelt auf.
    #
    (ordner / "apt_bricht").touch()

    ausgabe = install_funktion(ordner, umgebung, ["dmx_paket_sicherstellen"])

    assert apt_aufrufe(umgebung) == [], (
        "Das Paket ist da, trotzdem wurde apt-get aufgerufen: "
        + str(apt_aufrufe(umgebung))
    )
    assert "nicht installierbar" not in ausgabe, ausgabe

    print("OK: Ein vorhandenes Paket wird gar nicht erst angefasst")


with tempfile.TemporaryDirectory() as tmp:

    #
    # Paket fehlt, apt kann es holen.
    #
    ordner = Path(tmp)
    umgebung = werkzeuge(ordner, ordner / "olad.service")

    (ordner / "apt_legt").touch()

    ausgabe = install_funktion(ordner, umgebung, ["dmx_paket_sicherstellen"])

    assert len(apt_aufrufe(umgebung)) == 1, apt_aufrufe(umgebung)
    assert "nicht installierbar" not in ausgabe, ausgabe

    print("OK: Fehlt das Paket, wird es installiert")


with tempfile.TemporaryDirectory() as tmp:

    #
    # DER Fall, an dem es gescheitert ist: apt gibt einen Fehler
    # zurueck, das Paket liegt aber vor. Frueher hiess das "nicht
    # installierbar" und die ganze DMX-Einrichtung fiel aus.
    #
    ordner = Path(tmp)
    umgebung = werkzeuge(ordner, ordner / "olad.service")

    (ordner / "apt_bricht").touch()
    (ordner / "apt_legt").touch()      # apt meckert, legt es aber an

    skript = ordner / "lauf.sh"
    skript.write_text(
        "\n".join([
            "export XRACK_INSTALL_SOURCE_ONLY=1",
            f"source {INSTALL}",
            "dmx_paket_sicherstellen && echo ERGEBNIS_OK || echo ERGEBNIS_AUS",
        ]),
        encoding="utf-8",
    )

    lauf = subprocess.run(["bash", str(skript)], capture_output=True,
                          text=True, env=umgebung, timeout=60)

    assert "ERGEBNIS_OK" in lauf.stdout, (
        "apt hat gemeckert, das Paket liegt aber vor - trotzdem gilt die "
        "Lichtsteuerung als nicht verfügbar:\n" + lauf.stdout
    )

    print("OK: Meckert apt, ist das Paket aber da, geht es weiter")


with tempfile.TemporaryDirectory() as tmp:

    #
    # Und wenn es wirklich nicht geht: Meldung MIT Grund. Ohne den
    # sucht man an der falschen Stelle - genau das ist passiert.
    #
    ordner = Path(tmp)
    umgebung = werkzeuge(ordner, ordner / "olad.service")

    (ordner / "apt_bricht").touch()

    skript = ordner / "lauf.sh"
    skript.write_text(
        "\n".join([
            "export XRACK_INSTALL_SOURCE_ONLY=1",
            f"source {INSTALL}",
            "dmx_paket_sicherstellen && echo ERGEBNIS_OK || echo ERGEBNIS_AUS",
        ]),
        encoding="utf-8",
    )

    lauf = subprocess.run(["bash", str(skript)], capture_output=True,
                          text=True, env=umgebung, timeout=60)

    assert "ERGEBNIS_AUS" in lauf.stdout, lauf.stdout
    assert "nicht installierbar" in lauf.stdout, lauf.stdout
    assert "Unable to locate package" in lauf.stdout, (
        "Die Meldung nennt den Grund nicht - dann sucht man wieder an "
        "der falschen Stelle:\n" + lauf.stdout
    )

    print("OK: Geht es wirklich nicht, steht der Grund von apt dabei")


# --- "sudo VAR=wert" darf nirgends mehr stehen ----------------------
#
# Das ist die Sorte Fehler, die man beim naechsten Mal an anderer
# Stelle wieder einbaut. Kommentarzeilen zaehlen nicht mit - dort wird
# das Konstrukt absichtlich erwaehnt.

import re  # noqa: E402

for datei in [INSTALL] + sorted((INSTALL.parent / "scripts").glob("*.sh")):

    for nummer, zeile in enumerate(
        datei.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if zeile.lstrip().startswith("#"):
            continue

        assert not re.search(r"\bsudo\s+[A-Z_]+=", zeile), (
            f"{datei.name}:{nummer} setzt eine Umgebungsvariable direkt "
            f"hinter sudo - das haengt an der sudoers-Regel. "
            f"'sudo env VAR=wert' benutzen:\n    {zeile.strip()}"
        )

print("OK: Nirgends mehr 'sudo VAR=wert' statt 'sudo env VAR=wert'")


print("Alle DMX-Tests erfolgreich.")
