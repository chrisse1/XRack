#!/usr/bin/env python3
"""
Prüft, dass ein zweiter Lauf von install.sh nichts wegwirft.

Das ist kein Randfall: Ändert sich install.sh, fordert der Updater
ausdrücklich dazu auf, ihn noch einmal von Hand laufen zu lassen
(scripts/xrack-update.py) - sonst fehlen Systemeinstellungen. Genau auf
diesem Weg hat configure_basic_settings() vorher config/local.yaml
bedingungslos überschrieben:

  - Enter beim Port  -> zurück auf 8080, ein abweichender Port weg,
                        die Weboberfläche unter der alten Adresse tot.
  - Enter bei der PIN -> pin_hash leer, der Schutz der Einstellungen
                        stillschweigend abgeschaltet.
  - nicht interaktiv -> beides, ohne dass jemand gefragt wurde.

Geprüft wird der nicht interaktive Weg. Er ist der schärfere Fall (dort
wird gar nicht gefragt) und der einzige, der sich ohne Terminal
nachstellen lässt - beide Zweige lesen dieselben Vorgaben ein.

install.sh wird dafür nur eingelesen, nicht ausgeführt
(XRACK_INSTALL_SOURCE_ONLY), wie in test_wlan_setup.py und
test_dmx_control.py.
"""

import os
import subprocess
import tempfile
from pathlib import Path

import yaml


INSTALL = Path(__file__).resolve().parent / "install.sh"


def lauf(ordner: Path, inhalt: str | None, sprache: str = "de") -> dict:
    """
    Legt optional eine local.yaml an, ruft configure_basic_settings
    nicht interaktiv auf und liefert, was danach in der Datei steht.
    """

    datei = ordner / "local.yaml"

    if inhalt is not None:
        datei.write_text(inhalt, encoding="utf-8")

    skript = ordner / "lauf.sh"
    skript.write_text(
        "export XRACK_INSTALL_SOURCE_ONLY=1\n"
        f'export XRACK_LOCAL_CONFIG="{datei}"\n'
        f"source {INSTALL}\n"
        f'XRACK_LANGUAGE="{sprache}"\n'
        "configure_basic_settings >/dev/null\n",
        encoding="utf-8",
    )

    umgebung = dict(os.environ)
    umgebung["XRACK_LANGUAGE"] = sprache

    #
    # stdin auf /dev/null: So ist "[ -t 0 ]" falsch, also genau der
    # nicht interaktive Weg.
    #
    with open(os.devnull) as leer:

        ergebnis = subprocess.run(
            ["bash", str(skript)],
            stdin=leer, capture_output=True, text=True,
            env=umgebung, timeout=60,
        )

    assert ergebnis.returncode == 0, (ergebnis.returncode, ergebnis.stderr)

    return yaml.safe_load(datei.read_text(encoding="utf-8")) or {}


# ====================================================================
# 1. Eine vorhandene Einrichtung überlebt den zweiten Lauf
# ====================================================================

VORHANDEN = """application:
  language: "en"

server:
  port: 8443

security:
  pin_hash: "abc123def456"
"""

with tempfile.TemporaryDirectory() as tmp:

    #
    # choose_language() haette hier "de" gesetzt (die Vorgabe, wenn
    # niemand antwortet). Die gespeicherte Sprache muss trotzdem
    # gewinnen - sonst spraeche XRack nach einem stillen zweiten Lauf
    # ploetzlich Deutsch.
    #
    daten = lauf(Path(tmp), VORHANDEN, sprache="de")

    assert daten["server"]["port"] == 8443, (
        f"Der eingestellte Port wurde überschrieben: {daten['server']['port']}. "
        f"Die Weboberfläche wäre danach unter der alten Adresse tot."
    )

    assert daten["security"]["pin_hash"] == "abc123def456", (
        f"Der PIN-Schutz wurde stillschweigend abgeschaltet: "
        f"{daten['security']['pin_hash']!r}"
    )

    assert daten["application"]["language"] == "en", (
        f"Die eingestellte Sprache wurde überschrieben: "
        f"{daten['application']['language']}"
    )

    print("OK: Port, PIN und Sprache überleben einen zweiten Lauf")


# ====================================================================
# 2. Eine Neuinstallation verhält sich unverändert
#
# Die Gegenseite: Wer die Vorgaben durch das Einlesen ersetzt, baut
# leicht den umgekehrten Fehler ein.
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    daten = lauf(Path(tmp), None)

    assert daten["server"]["port"] == 8080, daten["server"]["port"]
    assert daten["security"]["pin_hash"] == "", daten["security"]["pin_hash"]
    assert daten["application"]["language"] == "de", daten["application"]

    print("OK: Ohne vorhandene Datei gelten weiter die Vorgaben")


# ====================================================================
# 3. Eine kaputte Datei hält die Installation nicht an
#
# Sie darf zu den Vorgaben führen, aber nicht zum Abbruch - sonst
# käme man nach einem halb geschriebenen Update nicht mehr weiter.
# ====================================================================

for kaputt in (
    "das ist kein yaml: [[[",
    "einfach nur text",
    "server: 8443\n",          # server ist hier kein Woerterbuch
    "",
):

    with tempfile.TemporaryDirectory() as tmp:

        daten = lauf(Path(tmp), kaputt)

        assert daten["server"]["port"] == 8080, (kaputt, daten)
        assert daten["security"]["pin_hash"] == "", (kaputt, daten)

print("OK: Eine unlesbare Datei führt zu den Vorgaben, nicht zum Abbruch")


print("Alle Installer-Einstellungstests erfolgreich.")
