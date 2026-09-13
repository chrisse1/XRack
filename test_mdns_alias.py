#!/usr/bin/env python3
"""
Prüft den gemeinsamen Zweitnamen im Netz (core/mdns_alias.py).

Anlass ist ein Bericht vom Tablet: Die als Web-App gespeicherte
Oberfläche startet immer genau die Adresse, unter der sie gespeichert
wurde - also etwa "xrack.local:8080". Steht im Proberaum ein anderes
XRack, tippt man auf sein Symbol und bekommt eine Fehlerseite. Ohne
Adressleiste (die Web-App hat keine) gibt es dann keinen Weg mehr,
eine andere Adresse einzugeben.

Abfangen lässt sich das im Browser nicht: Wenn der Rechner nicht
antwortet, läuft von XRack kein einziger Befehl - die Seite kommt ja
gar nicht erst an. Ein Service Worker könnte es, aber der ist auf
einem selbstsignierten Zertifikat gesperrt.

Deshalb der Weg über den Namen: Jedes XRack meldet zusätzlich zu
seinem eigenen einen GEMEINSAMEN Namen. Eine Web-App, einmal darunter
gespeichert, findet in jedem Raum das Gerät, das dort steht.

Geprüft wird gegen ein nachgestelltes "avahi-publish" im PATH, das
seine Aufrufe mitschreibt - wie in test_wlan_setup.py bei nmcli. Was
avahi im echten Netz daraus macht, kann nur ein Test am Gerät zeigen;
hier steht, dass XRack die richtigen Aufrufe absetzt, sie am Leben
hält und auf Adresswechsel und Namenskonflikt richtig reagiert.
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import core.mdns_alias as modul
from core.mdns_alias import MdnsAlias


#
# Ein avahi-publish, das seine Aufrufe protokolliert und dann liegen
# bleibt - genau wie das echte, das den Namen hält, solange es läuft.
#
FAKE_PUBLISH = """#!/usr/bin/env bash
echo "$*" >> "$ALIAS_LOG"
if [ -f "$ALIAS_KONFLIKT" ]; then
    echo "Failed to add address record: Local name collision"
    exit 1
fi
sleep 3600
"""


def umgebung_bauen(ordner: Path) -> dict:
    """PATH mit dem nachgestellten avahi-publish."""

    binordner = ordner / "bin"
    binordner.mkdir(parents=True, exist_ok=True)

    datei = binordner / "avahi-publish"
    datei.write_text(FAKE_PUBLISH, encoding="utf-8")
    datei.chmod(0o755)

    os.environ["PATH"] = f"{binordner}:{os.environ['PATH']}"
    os.environ["ALIAS_LOG"] = str(ordner / "aufrufe")
    os.environ["ALIAS_KONFLIKT"] = str(ordner / "konflikt")

    return {"log": ordner / "aufrufe", "konflikt": ordner / "konflikt"}


def aufrufe(pfad: Path) -> list[str]:

    if not pfad.exists():
        return []

    return [z for z in pfad.read_text(encoding="utf-8").splitlines() if z]


scratch = Path(tempfile.mkdtemp(prefix="xrack_mdns_"))

dateien = umgebung_bauen(scratch)

#
# Die Wache sieht im Betrieb alle fünf Sekunden nach. Für den Test
# wird der Takt heruntergesetzt - sonst dauert jeder Versuch fünf
# Sekunden, und die Testreihe soll zügig durchlaufen. Geprüft wird
# dadurch dasselbe, nur schneller.
#
modul.WACHINTERVALL = 0.05


# ====================================================================
# 1. Namen prüfen
#
# Was hier durchkommt, muss in jeder Adresszeile funktionieren -
# deshalb der enge Zeichensatz. Und der eigene Hostname taugt als
# GEMEINSAMER Name nicht: Ihn hätte jedes Gerät anders.
# ====================================================================

alias = MdnsAlias()

assert alias.pruefen("") == "", "Leer heißt 'kein Zweitname' und ist erlaubt."
assert alias.pruefen("xrack") == ""
assert alias.pruefen("xrack.local") == "", "Die Endung darf man mitschreiben."
assert alias.pruefen("x-rack-2") == ""

for schlecht in ("mein rack", "räck", "-xrack", "xrack-", "xrack.pi", "x/y"):
    assert alias.pruefen(schlecht), f"'{schlecht}' hätte auffallen müssen."

assert alias.pruefen(alias.hostname()), (
    "Der eigene Hostname taugt nicht als gemeinsamer Name."
)

print("OK: Brauchbare Namen kommen durch, unbrauchbare nicht")


# ====================================================================
# 2. Gemeldet wird EINE Adresse - und zwar eine erreichbare
#
# Hier stand einmal das Gegenteil: "der Name wird für JEDE Adresse
# gemeldet", weil das Tablet je nach Raum eine andere braucht. Am
# Gerät kam davon das hier zurück: "gelegentlich erreichbar, dann
# meldete der Browser eine Netzwerk-Zeitüberschreitung".
#
# Der Grund steckt in avahi-publish: Es kennt keine Option für eine
# Schnittstelle und meldet deshalb jede Adresse auf ALLEN. Ein Tablet
# im Heimnetz bekam damit zwei Antworten - die richtige und die der
# Access-Point-Brücke, die von dort aus niemand erreicht. Welche der
# Browser nimmt, entscheidet er selbst; nimmt er die falsche, wartet
# er bis zur Zeitüberschreitung.
#
# Der eigene Hostname hatte das Problem nie: Den meldet avahi-daemon
# selbst, und der antwortet je Schnittstelle passend. Genau deshalb
# war "x18rack.local" stabil und "xrack.local" sprunghaft.
# ====================================================================

#
# Der Normalfall am Gerät: Heimnetz-WLAN und die Brücke des Access
# Points. Die Standardroute geht über wlan0.
#
def netz(karte, standard=""):
    """Ein nachgestelltes Netz: Schnittstellen und die Standardroute."""

    alias.schnittstellen = lambda: karte
    alias.standard_schnittstelle = lambda: standard


netz({"wlan0": ["192.168.1.50"], "br0": ["10.42.0.1"]}, standard="wlan0")

erfolg, meldung = alias.setzen("xrack")

assert erfolg, meldung

time.sleep(0.3)

gemeldet = aufrufe(dateien["log"])

assert len(gemeldet) == 1, (
    f"Es wurde mehr als eine Adresse gemeldet - genau daran hing die "
    f"Zeitüberschreitung im Browser: {gemeldet}"
)

assert gemeldet[0].endswith("xrack.local 192.168.1.50"), (
    f"Gemeldet wurde nicht die erreichbare Adresse: {gemeldet}"
)

assert all("-a" in zeile for zeile in gemeldet), gemeldet

stand = alias.status()

assert stand["published"] is True, stand
assert stand["name"] == "xrack", stand
assert stand["addresses"] == ["192.168.1.50"], stand
assert stand["error"] == "", stand

print(f"OK: Gemeldet wird eine erreichbare Adresse ({gemeldet})")


# ====================================================================
# 2b. Ohne Heimnetz gilt der Access Point
#
# Der Proberaum: kein Heimnetz in Reichweite, die Tablets hängen am
# Access Point. Dann ist dessen Adresse die einzige, die es gibt -
# und sie MUSS gemeldet werden. Eine Auswahl, die hier nichts mehr
# findet, hätte den Proberaum kaputtgemacht, also genau den Fall, für
# den es den Zweitnamen gibt.
# ====================================================================

for karte, standard, erwartet, warum in (
    (
        {"br0": ["10.42.0.1"]},
        "",
        "10.42.0.1",
        "nur der Access Point",
    ),
    (
        {"br0": ["10.42.0.1"], "eth0": ["192.168.0.2"]},
        "",
        "10.42.0.1",
        "Access Point und Mischpult-Buchse, aber kein Weg nach draußen",
    ),
    (
        {"eth0": ["192.168.0.2"]},
        "",
        "192.168.0.2",
        "nur die Buchse",
    ),
    (
        {"wlan0": ["169.254.7.7"], "br0": ["10.42.0.1"]},
        "",
        "10.42.0.1",
        "eine selbstvergebene Adresse ist schlechter als der Access Point",
    ),
    (
        {"wlan0": ["169.254.7.7"]},
        "",
        "169.254.7.7",
        "selbstvergeben ist immer noch besser als gar kein Name",
    ),
    (
        {"eth0": ["192.168.0.2"], "wlan0": ["192.168.1.50"]},
        "wlan0",
        "192.168.1.50",
        "die Standardroute schlägt die Mischpult-Buchse",
    ),
):

    netz(karte, standard)

    assert alias.adressen() == [erwartet], (
        f"{warum}: erwartet {erwartet}, bekommen {alias.adressen()} "
        f"(Netz: {karte}, Standardroute: {standard!r})"
    )

print("OK: Ohne Heimnetz gilt der Access Point, sonst der Weg nach draußen")


# ====================================================================
# 2c. Die Auswahl liest ein echtes /proc/net/route
#
# Die Tabelle ist nicht schön, aber sie steht überall und kostet kein
# Werkzeug: Die Standardroute ist die Zeile mit dem Ziel 00000000.
# Ein Test, der nur die überschriebene Funktion prüft, hätte einen
# Lesefehler hier nie bemerkt.
# ====================================================================

echte = MdnsAlias()

routen = scratch / "route"

routen.write_text(
    "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\n"
    "br0\t00002A0A\t00000000\t0001\t0\t0\t0\t00FFFFFF\n"
    "wlan0\t00000000\t0101A8C0\t0003\t0\t0\t600\t00000000\n",
    encoding="utf-8",
)

modul.ROUTEN_DATEI = str(routen)

assert echte.standard_schnittstelle() == "wlan0", (
    f"Die Standardroute wurde nicht gefunden: "
    f"{echte.standard_schnittstelle()!r}"
)

#
# Und ohne Standardroute (Proberaum ohne Uplink) bleibt es leer,
# statt die erstbeste Zeile zu nehmen.
#
routen.write_text(
    "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\n"
    "br0\t00002A0A\t00000000\t0001\t0\t0\t0\t00FFFFFF\n",
    encoding="utf-8",
)

assert echte.standard_schnittstelle() == "", (
    "Ohne Standardroute wird eine beliebige Schnittstelle genommen."
)

modul.ROUTEN_DATEI = "/proc/net/route"

echte.stop()

print("OK: Die Standardroute wird aus /proc/net/route gelesen")


# ====================================================================
# 3. Abschalten beendet die Prozesse wirklich
#
# Ein liegengebliebener avahi-publish würde den Namen weiter belegen -
# und beim nächsten Einschalten mit sich selbst kollidieren.
# ====================================================================

kinder = list(alias._prozesse)

erfolg, meldung = alias.setzen("")

assert erfolg, meldung

for kind in kinder:
    assert kind.poll() is not None, "Ein avahi-publish läuft weiter."

assert alias.status()["published"] is False
assert alias.status()["name"] == ""

print("OK: Abschalten beendet die Meldungen")


# ====================================================================
# 4. Ein Adresswechsel wird nachgezogen
#
# Kabel raus, Access Point an - danach zeigt der alte Eintrag auf eine
# Adresse, die es nicht mehr gibt. Das ist schlimmer als gar kein
# Name.
# ====================================================================

dateien["log"].unlink(missing_ok=True)

netz({"wlan0": ["192.168.1.50"]}, standard="wlan0")

alias.setzen("xrack")

time.sleep(0.2)

alte_kinder = list(alias._prozesse)

#
# Jetzt hängt das Gerät woanders: Heimnetz weg, Access Point an.
#
netz({"br0": ["10.42.0.1"]}, standard="")

time.sleep(0.4)

gemeldet = aufrufe(dateien["log"])

assert any(zeile.endswith("xrack.local 10.42.0.1") for zeile in gemeldet), (
    f"Die neue Adresse wurde nicht gemeldet: {gemeldet}"
)

for kind in alte_kinder:
    assert kind.poll() is not None, (
        "Der Eintrag für die alte Adresse läuft weiter."
    )

assert alias.status()["addresses"] == ["10.42.0.1"], alias.status()

print("OK: Nach einem Adresswechsel steht der Name auf der neuen Adresse")


# ====================================================================
# 5. Namenskonflikt: melden, nicht im Sekundentakt weiterstreiten
#
# Genau der Fall, den es zu erwarten gibt: zwei XRacks mit demselben
# gemeinsamen Namen im selben Netz. avahi beendet dann den Prozess -
# und der Nutzer soll erfahren, warum sein Name nicht steht.
# ====================================================================

alias.setzen("")

dateien["konflikt"].write_text("ja", encoding="utf-8")
dateien["log"].unlink(missing_ok=True)

netz({"wlan0": ["192.168.1.50"]}, standard="wlan0")

alias.setzen("xrack")

#
# Der nachgestellte avahi-publish endet sofort - die Wache muss das
# merken.
#
time.sleep(0.4)

stand = alias.status()

assert stand["published"] is False, stand
assert stand["error"], "Der Konflikt wurde nicht gemeldet."
assert "collision" in stand["error"].lower() or "XRack" in stand["error"], (
    stand["error"]
)

print(f"OK: Ein Namenskonflikt wird gemeldet ({stand['error'][:60]}...)")

#
# Und danach ist Ruhe: Zwei Geräte, die sich im Sekundentakt um
# denselben Namen streiten, fluten nur das Netz.
#
vorher = len(aufrufe(dateien["log"]))

time.sleep(0.4)

assert len(aufrufe(dateien["log"])) == vorher, (
    "Nach einem Konflikt wird sofort weiterprobiert - das gibt einen "
    "Dauerstreit im Netz."
)

print("OK: Nach dem Konflikt wird nicht sofort weiterprobiert")


alias.stop()

dateien["konflikt"].unlink(missing_ok=True)


# ====================================================================
# 6. Ohne avahi-publish sagt XRack, was fehlt
#
# Sonst trägt man einen Namen ein, es passiert nichts, und niemand
# erfährt warum.
# ====================================================================

os.environ["PATH"] = "/nichts-da"

ohne = MdnsAlias()

assert ohne.verfuegbar is False

erfolg, meldung = ohne.setzen("xrack")

assert erfolg is False
assert "avahi-utils" in meldung, meldung

#
# Abschalten muss trotzdem gehen - sonst käme man aus einem
# eingetragenen Namen nicht mehr heraus.
#
erfolg, _ = ohne.setzen("")

assert erfolg is True

ohne.stop()

print("OK: Fehlt avahi-publish, wird das gesagt statt still nichts zu tun")


import shutil  # noqa: E402

shutil.rmtree(scratch, ignore_errors=True)

print("Alle Zweitnamen-Tests erfolgreich.")
