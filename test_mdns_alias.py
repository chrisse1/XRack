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
# 2. Der Name wird für JEDE Adresse gemeldet
#
# Welche Adresse das Tablet erreicht, hängt am Raum: über den Access
# Point ist es eine andere als über das Kabel, und beide gleichzeitig
# gibt es auch. Wird nur eine gemeldet, zeigt der Name im falschen
# Netz ins Leere.
# ====================================================================

alias.adressen = lambda: ["192.168.1.50", "10.42.0.1"]

erfolg, meldung = alias.setzen("xrack")

assert erfolg, meldung

time.sleep(0.3)

gemeldet = aufrufe(dateien["log"])

assert len(gemeldet) == 2, f"Erwartet zwei Aufrufe, gefunden: {gemeldet}"

for adresse in ("192.168.1.50", "10.42.0.1"):
    assert any(
        zeile.endswith(f"xrack.local {adresse}") for zeile in gemeldet
    ), f"Für {adresse} wurde nichts gemeldet: {gemeldet}"

assert all("-a" in zeile for zeile in gemeldet), gemeldet

stand = alias.status()

assert stand["published"] is True, stand
assert stand["name"] == "xrack", stand
assert stand["addresses"] == ["192.168.1.50", "10.42.0.1"], stand
assert stand["error"] == "", stand

print(f"OK: Der Name wird für jede Adresse gemeldet ({gemeldet})")


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

alias.adressen = lambda: ["192.168.1.50"]

alias.setzen("xrack")

time.sleep(0.2)

alte_kinder = list(alias._prozesse)

#
# Jetzt hängt das Gerät woanders.
#
alias.adressen = lambda: ["10.42.0.1"]

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

alias.adressen = lambda: ["192.168.1.50"]

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
