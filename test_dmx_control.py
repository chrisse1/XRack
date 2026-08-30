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

import json
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
    """
    Nimmt POSTs entgegen, merkt sich den Inhalt - und fuehrt Buch
    ueber Anschluesse und Universen.

    Das Buchfuehren ist noetig, weil XRack nach einer Zuordnung
    nachsieht, ob sie wirklich angekommen ist. Eine Attrappe, die
    jeden Auftrag mit "ok" beantwortet und sonst nichts tut, koennte
    genau diesen Teil nicht pruefen - und der ist der wichtigste:
    olad antwortet auch dann mit 200, wenn die Zuordnung im
    Hintergrund scheitert.
    """

    empfangen = []
    abfragen = []
    antwort_code = 200

    #
    # Der Anfangszustand nach der Installation: Anschluesse da,
    # keiner einem Universum zugeordnet.
    #
    frei = []
    universen = []
    zugeordnet = []

    #
    # Damit sich der Fall nachstellen laesst, dass olad den Auftrag
    # freundlich annimmt und trotzdem nichts patcht.
    #
    stur = False

    @classmethod
    def zuruecksetzen(cls, frei=None):

        cls.empfangen = []
        cls.abfragen = []
        cls.antwort_code = 200
        cls.stur = False
        cls.universen = []
        cls.zugeordnet = []
        cls.frei = list(frei or [])

    @classmethod
    def _uebernehmen(cls, felder):
        """Wie olad: add_ports zuordnen, remove_ports wieder freigeben."""

        if cls.stur:
            return

        for kennung in felder.get("remove_ports", [""])[0].split(","):

            port = next(
                (p for p in cls.zugeordnet if p["id"] == kennung), None
            )

            if port is not None:
                cls.zugeordnet.remove(port)
                cls.frei.append(port)

        for kennung in felder.get("add_ports", [""])[0].split(","):

            port = next((p for p in cls.frei if p["id"] == kennung), None)

            if port is not None:
                cls.frei.remove(port)
                cls.zugeordnet.append(port)

        cls.universen = [{
            "id": 1,
            "name": felder.get("name", ["-"])[0],
            "input_ports": 0,
            "output_ports": len(
                [p for p in cls.zugeordnet if p.get("is_output")]
            ),
        }]

    def _antworten(self, inhalt, code=200):

        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(inhalt.encode("utf-8"))

    def do_POST(self):

        laenge = int(self.headers.get("Content-Length", 0))
        koerper = self.rfile.read(laenge).decode("ascii")

        OladAttrappe.empfangen.append((self.path, koerper))

        if self.path in ("/new_universe", "/modify_universe"):
            OladAttrappe._uebernehmen(urllib.parse.parse_qs(koerper))

        self.send_response(OladAttrappe.antwort_code)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_GET(self):

        pfad = self.path.split("?", 1)[0]

        OladAttrappe.abfragen.append(pfad)

        if pfad == "/json/universe_plugin_list":
            self._antworten(json.dumps({
                "universes": OladAttrappe.universen,
                "plugins": [],
            }))
            return

        if pfad == "/json/get_ports":
            self._antworten(json.dumps(OladAttrappe.frei))
            return

        if pfad == "/json/universe_info":

            #
            # Genau wie olad: Gibt es das Universum nicht, kommt ein
            # Fehler zurueck - keine leere Liste.
            #
            if not OladAttrappe.universen:
                self._antworten("Universe doesn't exist", 500)
                return

            self._antworten(json.dumps({
                "id": 1,
                "name": OladAttrappe.universen[0]["name"],
                "merge_mode": "HTP",
                "input_ports": [
                    p for p in OladAttrappe.zugeordnet
                    if not p.get("is_output")
                ],
                "output_ports": [
                    p for p in OladAttrappe.zugeordnet if p.get("is_output")
                ],
            }))
            return

        self._antworten("OLA")

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

    #
    # Ohne zugeordneten Ausgang sieht von aussen alles heil aus:
    # Dienst laeuft, Kabel steckt, Senden meldet Erfolg - und es
    # bleibt dunkel. Deshalb muss die Zuordnung mit im Bericht
    # stehen, sonst kann die Oberflaeche den Fall nicht benennen.
    #
    assert stand["patched"] is False, stand

    print("OK: Der Statusbericht nennt Dienst, Kabel, Universum und Zuordnung")

    server.shutdown()
    server.server_close()


# ====================================================================
# 8. Den Ausgang dem Universum zuordnen
#
# Nach der Installation kennt olad das Kabel, schickt aber noch
# nichts hinaus: Der Anschluss muss erst einem Universum zugeordnet
# werden. Auf der Kommandozeile ist das "ola_patch -d .. -p .. -u 1";
# XRack macht denselben Schritt ueber die Web-Schnittstelle, damit
# niemand dafuer ein Terminal braucht.
# ====================================================================

ANSCHLUESSE = [
    {"device": "FT232R USB UART", "description": "Serial: A50285BI",
     "id": "2-O-0", "is_output": True},
    {"device": "FT232R USB UART", "description": "Serial: A50285BI",
     "id": "2-O-1", "is_output": True},
    {"device": "Dummy Device", "description": "Dummy Port 0",
     "id": "1-O-0", "is_output": True},
    {"device": "E1.31 (DMX over ACN)", "description": "Universe 1",
     "id": "3-I-0", "is_output": False},
]


def frische_attrappe() -> tuple:
    """Ein Dienst im Zustand direkt nach der Installation."""

    OladAttrappe.zuruecksetzen([dict(port) for port in ANSCHLUESSE])

    return dienst_starten()


server, adresse = frische_attrappe()

dmx = DmxControl(base_url=adresse)

anschluesse = dmx.ports()

#
# Eingaenge gehoeren nicht in die Auswahl: Dorthin kann XRack nichts
# schicken.
#
assert [port["id"] for port in anschluesse] == ["2-O-0", "2-O-1", "1-O-0"], (
    anschluesse
)

#
# Der Anschluss des Dummy-Plugins fuehrt nirgendwohin. Verstecken
# waere falsch - zum Ausprobieren ist er gedacht -, aber er darf
# nicht obenan stehen, sonst zeigt der erste Vorschlag auf einen
# Anschluss, an dem garantiert keine Lampe haengt.
#
assert anschluesse[-1]["device"] == "Dummy Device", anschluesse

assert anschluesse[0]["label"] == (
    "FT232R USB UART - Serial: A50285BI (Ausgang 0)"
), anschluesse[0]

assert not any(port["patched"] for port in anschluesse), anschluesse
assert dmx.patched is False, "Ohne Universum darf nichts zugeordnet sein."

print("OK: Die Auswahl nennt nur Ausgänge, Dummy zuletzt")


# --------------------------------------------------------------------
# Unsinn wird abgewiesen, bevor olad davon erfaehrt
# --------------------------------------------------------------------

OladAttrappe.empfangen = []

for unsinn in ("3-I-0", "quatsch", "", "2-O"):

    erfolg, meldung = dmx.patch(unsinn)

    assert erfolg is False, f"'{unsinn}' wurde als Ausgang angenommen."
    assert meldung, "Ein Fehlschlag ohne Begründung hilft niemandem."

assert OladAttrappe.empfangen == [], (
    "Für eine unsinnige Kennung darf gar kein Auftrag hinausgehen: "
    f"{OladAttrappe.empfangen}"
)

print("OK: Eingänge und Unsinn werden abgewiesen, ohne olad zu behelligen")


# --------------------------------------------------------------------
# Die erste Zuordnung: Das Universum gibt es noch gar nicht
# --------------------------------------------------------------------

OladAttrappe.empfangen = []

erfolg, meldung = dmx.patch("2-O-1")

assert erfolg is True, meldung

pfad, koerper = OladAttrappe.empfangen[-1]
felder = urllib.parse.parse_qs(koerper)

assert pfad == "/new_universe", (
    "Gibt es noch kein Universum, muss es angelegt werden: " + pfad
)
assert felder["id"] == ["1"], felder
assert felder["add_ports"] == ["2-O-1"], felder

assert dmx.patched is True, "Nach der Zuordnung muss der Stand umspringen."

anschluesse = dmx.ports()

#
# Der zugeordnete Anschluss taucht bei olad nicht mehr unter den
# freien auf. Faende XRack ihn deshalb nicht mehr, verschwaende er
# aus der Auswahl - und niemand koennte sehen, worauf gesendet wird.
#
zugeordnet = [port for port in anschluesse if port["patched"]]

assert [port["id"] for port in zugeordnet] == ["2-O-1"], anschluesse
assert len(anschluesse) == 3, anschluesse

print("OK: Die erste Zuordnung legt das Universum an und bleibt sichtbar")


# --------------------------------------------------------------------
# Die zweite Zuordnung ersetzt die erste
#
# Genau der Fall, um den es geht: Beim ersten Mal wurde der falsche
# Anschluss erwischt. Bliebe er drin, braeuchte man doch wieder ein
# Terminal, um ihn loszuwerden.
# --------------------------------------------------------------------

OladAttrappe.universen[0]["name"] = "Bühne"
OladAttrappe.empfangen = []

erfolg, meldung = dmx.patch("2-O-0")

assert erfolg is True, meldung

pfad, koerper = OladAttrappe.empfangen[-1]
felder = urllib.parse.parse_qs(koerper)

assert pfad == "/modify_universe", (
    "Ein vorhandenes Universum wird geändert, nicht neu angelegt: " + pfad
)
assert felder["add_ports"] == ["2-O-0"], felder
assert felder["remove_ports"] == ["2-O-1"], felder

#
# modify_universe verlangt einen Namen. Waere hier stur "XRack"
# eingesetzt, bekaeme ein von Hand vergebener Name bei jeder
# Zuordnung einen Tritt.
#
assert felder["name"] == ["Bühne"], felder

zugeordnet = [port["id"] for port in dmx.ports() if port["patched"]]

assert zugeordnet == ["2-O-0"], zugeordnet

print("OK: Ein neuer Ausgang ersetzt den alten und behält den Namen")


# --------------------------------------------------------------------
# Nachsehen statt glauben
#
# olad beantwortet den Auftrag auch dann mit 200, wenn die Zuordnung
# im Hintergrund scheitert - etwa weil ein anderes Plugin das Kabel
# haelt. Ein "hat geklappt" waere dann die schlechteste aller
# Antworten: Man sucht den Fehler ueberall, nur nicht hier.
# --------------------------------------------------------------------

server.shutdown()
server.server_close()

server, adresse = frische_attrappe()

OladAttrappe.stur = True

dmx = DmxControl(base_url=adresse)

erfolg, meldung = dmx.patch("2-O-0")

assert erfolg is False, (
    "Eine Zuordnung, die nicht ankommt, darf nicht als Erfolg gelten."
)
assert "Kabel" in meldung, meldung

print("OK: Eine folgenlose Zuordnung wird als Fehlschlag gemeldet")

server.shutdown()
server.server_close()


# --------------------------------------------------------------------
# Der Merker: Die Lichtkarte fragt zweimal je Sekunde
# --------------------------------------------------------------------

server, adresse = frische_attrappe()

dmx = DmxControl(base_url=adresse)

OladAttrappe.abfragen = []

for _ in range(5):
    dmx.patched

assert OladAttrappe.abfragen.count("/json/universe_plugin_list") == 1, (
    "Die Zuordnung darf nicht bei jedem Statusabruf neu erfragt werden: "
    + str(OladAttrappe.abfragen)
)

#
# Nach einer Zuordnung muss der Merker aber weg sein, sonst zeigte
# die Karte noch fuenf Sekunden lang den alten Stand - und der
# Nutzer haelt die Zuordnung fuer misslungen.
#
dmx.patch("2-O-0")

OladAttrappe.abfragen = []

assert dmx.patched is True, "Nach dem Zuordnen muss neu nachgesehen werden."
assert OladAttrappe.abfragen.count("/json/universe_plugin_list") == 1, (
    OladAttrappe.abfragen
)

print("OK: Der Merker spart Abfragen, gilt aber nach einer Zuordnung nicht mehr")

server.shutdown()
server.server_close()


# --------------------------------------------------------------------
# Ohne Dienst darf nichts fliegen
# --------------------------------------------------------------------

tot = DmxControl(base_url=adresse)

assert tot.ports() == [], "Ohne Dienst muss die Auswahl leer bleiben."
assert tot.patched is False, "Ohne Dienst kann nichts zugeordnet sein."

erfolg, meldung = tot.patch("2-O-0")

assert erfolg is False and meldung, "Ohne Dienst muss die Zuordnung scheitern."

print("OK: Ohne Lichtdienst bleibt die Auswahl leer, ohne Absturz")


# ====================================================================
# 9. Die Einrichtung in install.sh
#
# Zwei Hilfsfunktionen dort haben echte Logik, und beide scheitern
# leise, wenn sie schiefgehen: Das Plugin bliebe stumm aus, oder
# OLAs ungeschützte Weboberfläche bliebe im Netzwerk erreichbar.
# Deshalb werden sie hier mit nachgestellten Werkzeugen durchgespielt
# - install.sh wird dafür nur eingelesen, nicht ausgeführt
# (XRACK_INSTALL_SOURCE_ONLY), wie in test_wlan_setup.py.
# ====================================================================

INSTALL = Path(__file__).resolve().parent / "install.sh"

FAKE_SUDO = (
    "#!/bin/sh\n"
    "# sudo wegdenken: ausfuehren, was dahinter steht.\n"
    "#\n"
    "# Ausser bei 'sudo -v': Das holt nur die Berechtigung und\n"
    "# fuehrt gar nichts aus - 'exec -v' waere ein Fehler.\n"
    '[ "$1" = "-v" ] && exit 0\n'
    'exec "$@"\n'
)

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
        #
        # configure_dmx sucht die Unit ueber "list-unit-files". Ohne
        # eine Antwort darauf kaeme es nie ueber die Suche hinaus.
        #
        'if [ "$1" = "list-unit-files" ]; then\n'
        '    echo "$2 enabled"\n'
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

    #
    # udevadm gibt es in dieser Umgebung nicht - configure_dmx ruft
    # es aber auf. Ohne Attrappe kaeme der Test nicht ueber die
    # udev-Regel hinaus.
    #
    FAKE_UDEVADM = "#!/bin/sh\nexit 0\n"
    #
    # Das Zuhause des Dienstbenutzers liegt im Testordner: Dort sucht
    # configure_dmx die Plugin-Einstellungen (<home>/.ola), und dort
    # darf ein Test auch schreiben.
    #
    olad_home = ordner / "olad-home"
    (olad_home / ".ola").mkdir(parents=True, exist_ok=True)

    FAKE_GETENT = (
        "#!/bin/sh\n"
        'if [ "$1" = "passwd" ] && [ "$2" = "olad" ]; then\n'
        f"    echo 'olad:x:102:65534::{olad_home}:/usr/sbin/nologin'\n"
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
        ("udevadm", FAKE_UDEVADM),
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

    #
    # Damit configure_dmx als Ganzes laufen kann, ohne ins echte
    # System zu schreiben.
    #
    umgebung["XRACK_UDEV_RULES"] = str(ordner / "99-xrack-dmx.rules")
    umgebung["XRACK_OLA_LOG"] = str(ordner / "ola.log")

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
# 10. Die eigene Unit muss auch eingeschaltet werden
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
# 11. Die Paketpruefung darf nicht falsch anschlagen
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


# ====================================================================
# 12. Ein ausgefallenes Licht muss am Ende dastehen
#
# Am zweiten Geraet gemeldet: Der Installer lief, die Lichtsteuerung
# fehlte danach - und im langen Protokoll war nicht zu finden, warum.
# Die Meldung stand mittendrin, danach kam noch eine halbe Seite und
# ein "Fertig.". Wer nicht zurueckscrollt, haelt die Installation fuer
# vollstaendig.
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    ordner = Path(tmp)
    umgebung = werkzeuge(ordner, ordner / "olad.service")

    #
    # Paket fehlt und apt kann es nicht holen.
    #
    (ordner / "apt_bricht").touch()

    ausgabe = install_funktion(ordner, umgebung, [
        "configure_dmx", "licht_zusammenfassung",
    ])

    assert "NICHT eingerichtet" in ausgabe, (
        "Die Zusammenfassung verschweigt, dass das Licht ausgefallen ist: "
        + ausgabe
    )

    assert "ola" in ausgabe, ausgabe

    assert "--dmx" in ausgabe, (
        "Ohne den Hinweis muss man fuer einen einzigen Schritt den "
        "ganzen Installer noch einmal durchlaufen: " + ausgabe
    )

    #
    # Und der Grund muss die Meldung ueberleben - im Protokoll steht,
    # was apt gesagt hat.
    #
    logdatei = Path(umgebung["XRACK_OLA_LOG"])

    assert logdatei.exists(), "Die apt-Ausgabe wurde nicht aufgehoben."
    assert logdatei.read_text(encoding="utf-8").strip(), logdatei

    assert str(logdatei) in ausgabe, (
        "Die Zusammenfassung nennt die Logdatei nicht: " + ausgabe
    )

    print("OK: Ein ausgefallenes Licht steht in der Zusammenfassung, mit Grund")


with tempfile.TemporaryDirectory() as tmp:

    ordner = Path(tmp)
    umgebung = werkzeuge(ordner, ordner / "olad.service")

    (ordner / "paket_da").touch()
    ausgabe = install_funktion(ordner, umgebung, [
        "configure_dmx", "licht_zusammenfassung",
    ])

    assert "NICHT" not in ausgabe, (
        "Bei erfolgreicher Einrichtung darf da kein 'NICHT' stehen: " + ausgabe
    )
    assert "Zuordnen" in ausgabe, (
        "Der noch fehlende Schritt - den Ausgang zuordnen - muss dastehen: "
        + ausgabe
    )

    print("OK: Ist das Licht eingerichtet, nennt die Zusammenfassung den Rest")


# ====================================================================
# 13. "install.sh --dmx" holt nur das Licht nach
#
# Faellt die Lichteinrichtung aus, ist genau EIN Schritt nachzuholen.
# Dafuer den ganzen Installer samt Netzwerkfragen noch einmal
# durchzugehen ist so muehsam, dass man es lieber laesst - und dann
# bleibt es eben dunkel.
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    ordner = Path(tmp)
    umgebung = werkzeuge(ordner, ordner / "olad.service")

    (ordner / "paket_da").touch()
    lauf = subprocess.run(
        ["bash", str(INSTALL), "--dmx"],
        capture_output=True, text=True, env=umgebung, timeout=120,
        cwd=str(Path(INSTALL).parent),
    )

    assert lauf.returncode == 0, (lauf.returncode, lauf.stderr[-1500:])

    #
    # Die Einrichtung ist gelaufen ...
    #
    assert Path(umgebung["XRACK_UDEV_RULES"]).exists(), (
        "Die udev-Regel wurde nicht geschrieben: " + lauf.stdout
    )

    assert any("enable" in zeile for zeile in systemctl_aufrufe(umgebung)), (
        systemctl_aufrufe(umgebung)
    )

    assert "Licht" in lauf.stdout, lauf.stdout

    #
    # ... und sonst nichts. Keine Systempakete, keine Fragen.
    #
    assert apt_aufrufe(umgebung) == [], (
        "'--dmx' hat Systempakete angefasst: " + str(apt_aufrufe(umgebung))
    )

    assert "Willkommen" not in lauf.stdout, lauf.stdout
    assert "Netzwerkkonfiguration" not in lauf.stdout, lauf.stdout

    print("OK: '--dmx' richtet nur das Licht ein und fasst sonst nichts an")


print("Alle DMX-Tests erfolgreich.")
