#!/usr/bin/env python3
"""
Konfiguration: default.yaml, die Ueberlagerung durch local.yaml und
das Schreiben einzelner Werte.

Anlass: Als auf einem Geraet ploetzlich Version 1.2.0 stand, habe ich
die local.yaml verdaechtigt - sie koennte ja eine alte Version
festhalten. Das Nachsehen im Quelltext dauerte mehrere Schritte; ein
Test haette es in Sekunden geklaert. Genau dafuer steht er hier.
"""

import sys
import tempfile
from pathlib import Path

from core.configuration import Configuration, _deep_merge

VOLLSTAENDIG = """
application:
  name: "XRack"
  version: "1.8.3"
  language: "de"

server:
  host: "0.0.0.0"
  port: 8080
  ssl_certfile: "certs/xrack.crt"
  ssl_keyfile: "certs/xrack.key"

security:
  pin_hash: ""

audio:
  sample_rate: 48000

recording:
  directory: "./recordings"

music:
  directory: "./music"

logging:
  level: "INFO"

update:
  repository: "chrisse1/XRack"
  branch: "main"
"""


def aufbau(tmp: Path, lokal: str | None = None) -> Configuration:

    (tmp / "config").mkdir(exist_ok=True)
    (tmp / "config" / "default.yaml").write_text(VOLLSTAENDIG, encoding="utf-8")

    if lokal is not None:
        (tmp / "config" / "local.yaml").write_text(lokal, encoding="utf-8")

    return Configuration(
        filename=str(tmp / "config" / "default.yaml"),
        local_filename=str(tmp / "config" / "local.yaml"),
    )


# ====================================================================
# Ohne local.yaml gilt die Voreinstellung
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    k = aufbau(Path(tmp))
    k.load()

    assert k.data.application.version == "1.8.3"
    assert k.data.application.language == "de"
    assert k.data.server.port == 8080

    print("OK: Ohne local.yaml gilt default.yaml")


# ====================================================================
# local.yaml ueberlagert nur, was darin steht
#
# Der Punkt: Sie ersetzt den Abschnitt NICHT, sie ergaenzt ihn. Sonst
# waere mit einer gesetzten Sprache der Name weg.
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    k = aufbau(Path(tmp), 'application:\n  language: "en"\n\nserver:\n  port: 9000\n')
    k.load()

    assert k.data.application.language == "en", "Ueberlagerung greift nicht"
    assert k.data.server.port == 9000

    assert k.data.application.name == "XRack", (
        "Der uebrige Abschnitt wurde ueberschrieben statt ergaenzt."
    )
    assert k.data.application.version == "1.8.3", (
        "Die Version kam aus local.yaml statt aus default.yaml - genau der "
        "Verdacht, den ich einmal hatte."
    )

    print("OK: local.yaml ergaenzt den Abschnitt, statt ihn zu ersetzen")


# ====================================================================
# Eine leere local.yaml darf nichts kaputtmachen
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    k = aufbau(Path(tmp), "")
    k.load()

    assert k.data.server.port == 8080

    print("OK: Eine leere local.yaml wird uebergangen")


# ====================================================================
# set_override schreibt, ohne anderes zu verlieren
#
# Das war der ausdrueckliche Zweck der Funktion: Sprache aendern, ohne
# einen zuvor gesetzten Port zu ueberschreiben.
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    k = aufbau(Path(tmp))

    k.set_override("server", "port", 9443)
    k.set_override("application", "language", "en")
    k.set_override("security", "pin_hash", "abc123")

    k.load()

    assert k.data.server.port == 9443
    assert k.data.application.language == "en"
    assert k.data.security.pin_hash == "abc123"

    #
    # Und ein zweiter Schreibvorgang im selben Abschnitt loescht den
    # ersten nicht.
    #
    k.set_override("server", "host", "127.0.0.1")
    k.load()

    assert k.data.server.port == 9443, (
        "Der Port ging beim Schreiben des Hosts verloren."
    )
    assert k.data.server.host == "127.0.0.1"

    print("OK: set_override behaelt bereits gespeicherte Werte")


# ====================================================================
# data() vor load() ist ein Fehler, kein stiller Leerwert
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    k = aufbau(Path(tmp))

    try:
        k.data
    except RuntimeError:
        pass
    else:
        raise AssertionError(
            "data() lieferte etwas, obwohl noch nichts geladen war."
        )

    print("OK: Zugriff vor dem Laden meldet einen Fehler")


# ====================================================================
# _deep_merge im Einzelnen
# ====================================================================

assert _deep_merge({"a": {"x": 1, "y": 2}}, {"a": {"y": 9}}) == {"a": {"x": 1, "y": 9}}
assert _deep_merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}

#
# Ein Wert ersetzt ein Woerterbuch und umgekehrt - ohne Absturz.
#
assert _deep_merge({"a": {"x": 1}}, {"a": 5}) == {"a": 5}
assert _deep_merge({"a": 5}, {"a": {"x": 1}}) == {"a": {"x": 1}}

#
# Die Vorlage darf dabei nicht veraendert werden: load() wird mehrfach
# aufgerufen, und ein veraendertes Original wuerde sich aufsummieren.
#
vorlage = {"a": {"x": 1}}
_deep_merge(vorlage, {"a": {"x": 99}})
assert vorlage == {"a": {"x": 1}}, f"Die Vorlage wurde veraendert: {vorlage}"

print("OK: _deep_merge fuehrt tief zusammen und laesst die Vorlage in Ruhe")

print("Alle Konfigurations-Tests erfolgreich.")
