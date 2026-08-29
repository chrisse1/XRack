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


# ====================================================================
# 4. Ein vorhandenes TLS-Zertifikat wird behalten
#
# Vorher wurde bei jedem Lauf ein neues erzeugt. Das war vertretbar,
# solange man den Installer selten startete - nur muss man ihn nach
# einem Update mit geaenderter install.sh ausdruecklich noch einmal
# laufen lassen, und dann waere auf JEDEM Handy, Tablet und Rechner
# die Sicherheitswarnung wieder da und muesste neu bestaetigt werden.
#
# Der Grund fuers Neuerzeugen war ein moeglicherweise geaenderter
# Hostname. Genau das laesst sich nachsehen, statt es vorsorglich
# anzunehmen.
# ====================================================================

def zertifikat_bauen(ordner: Path, hostname: str, tage: int) -> None:
    """Ein echtes Zertifikat mit openssl - keine Attrappe."""

    (ordner / "certs").mkdir(exist_ok=True)

    subprocess.run(
        [
            "openssl", "req", "-x509", "-nodes", "-newkey", "rsa:2048",
            "-keyout", str(ordner / "certs" / "xrack.key"),
            "-out", str(ordner / "certs" / "xrack.crt"),
            "-days", str(tage),
            "-subj", f"/CN={hostname}",
            "-addext",
            f"subjectAltName=DNS:{hostname},DNS:{hostname}.local,"
            "DNS:localhost,IP:127.0.0.1",
        ],
        capture_output=True, timeout=60, check=True,
    )


def passt(ordner: Path, hostname: str) -> bool:
    """Ruft zertifikat_passt aus install.sh auf."""

    skript = ordner / "zert.sh"
    skript.write_text(
        "export XRACK_INSTALL_SOURCE_ONLY=1\n"
        f"source {INSTALL}\n"
        f'INSTALL_DIR="{ordner}"\n'
        f'XRACK_HOSTNAME="{hostname}"\n'
        "zertifikat_passt\n",
        encoding="utf-8",
    )

    return subprocess.run(
        ["bash", str(skript)], capture_output=True, timeout=60
    ).returncode == 0


with tempfile.TemporaryDirectory() as tmp:

    ordner = Path(tmp)

    zertifikat_bauen(ordner, "xrack", 3650)

    assert passt(ordner, "xrack"), (
        "Ein passendes Zertifikat wird verworfen - jede Browser-Ausnahme "
        "müsste danach neu bestätigt werden."
    )

    #
    # Auf den GENAUEN Eintrag geprueft, nicht auf das Vorkommen: Sonst
    # wuerde bei Hostname "xra" ein Zertifikat fuer "xrack" passen,
    # und der Browser bekaeme eines, das seinen Namen gar nicht nennt.
    #
    assert not passt(ordner, "xra"), (
        "Ein Zertifikat für 'xrack' gilt fälschlich auch für 'xra'."
    )
    assert not passt(ordner, "xrackstudio"), (
        "Ein Zertifikat für 'xrack' gilt fälschlich auch für 'xrackstudio'."
    )
    assert not passt(ordner, "x18rack"), (
        "Ein geänderter Hostname muss ein neues Zertifikat auslösen."
    )

    print("OK: Ein passendes Zertifikat bleibt, ein fremder Name nicht")


with tempfile.TemporaryDirectory() as tmp:

    #
    # Ein bald ablaufendes Zertifikat stillschweigend zu behalten
    # waere die schlechteste aller Moeglichkeiten.
    #
    ordner = Path(tmp)

    zertifikat_bauen(ordner, "xrack", 10)

    assert not passt(ordner, "xrack"), (
        "Ein in 10 Tagen ablaufendes Zertifikat wird behalten."
    )

    print("OK: Ein bald ablaufendes Zertifikat wird erneuert")


with tempfile.TemporaryDirectory() as tmp:

    ordner = Path(tmp)

    assert not passt(ordner, "xrack"), "Ohne Zertifikat muss neu erzeugt werden."

    zertifikat_bauen(ordner, "xrack", 3650)
    (ordner / "certs" / "xrack.key").unlink()

    assert not passt(ordner, "xrack"), (
        "Ohne Schlüssel nützt das Zertifikat nichts - es muss neu erzeugt "
        "werden."
    )

    print("OK: Fehlt Zertifikat oder Schlüssel, wird neu erzeugt")


# ====================================================================
# 5. Der Access-Point-Name faellt nicht auf "XRack" zurueck
#
# Vorher war "XRack" der feste Vorgabename. Wer seinen Access Point
# anders genannt hatte, das Passwort beim zweiten Lauf aber neu
# eintippte (weil leer den Schritt ueberspringt, tun das viele), und
# beim Namen nur Enter drueckte, benannte ihn stillschweigend um -
# und jedes gekoppelte Handy fand das Netz nicht mehr.
# ====================================================================

def ap_vorgabe(ordner: Path, conf_inhalt: str | None) -> str:
    """Ruft ap_ssid_vorgabe aus install.sh auf."""

    conf = ordner / "hostapd.conf"

    if conf_inhalt is not None:
        conf.write_text(conf_inhalt, encoding="utf-8")

    #
    # sudo wegdenken: Der Test laeuft nicht als root, und geprueft
    # wird hier das Auslesen, nicht die Rechtevergabe.
    #
    binordner = ordner / "bin"
    binordner.mkdir(exist_ok=True)

    fake_sudo = binordner / "sudo"
    fake_sudo.write_text('#!/bin/sh\nexec "$@"\n', encoding="utf-8")
    fake_sudo.chmod(0o755)

    skript = ordner / "ap.sh"
    skript.write_text(
        "export XRACK_INSTALL_SOURCE_ONLY=1\n"
        f'export XRACK_HOSTAPD_CONF="{conf}"\n'
        f"source {INSTALL}\n"
        "ap_ssid_vorgabe\n",
        encoding="utf-8",
    )

    umgebung = dict(os.environ)
    umgebung["PATH"] = f"{binordner}:{os.environ['PATH']}"

    return subprocess.run(
        ["bash", str(skript)], capture_output=True, text=True,
        env=umgebung, timeout=60,
    ).stdout.strip()


AP_CONF = """interface=wlan1
ssid=Bandbus
wpa_passphrase=geheim123
country_code=DE
"""

with tempfile.TemporaryDirectory() as tmp:

    assert ap_vorgabe(Path(tmp), AP_CONF) == "Bandbus", (
        "Der eingerichtete Access-Point-Name wird nicht übernommen - "
        "Enter würde ihn auf 'XRack' umbenennen."
    )

    print("OK: Der eingerichtete Access-Point-Name ist die Vorgabe")


with tempfile.TemporaryDirectory() as tmp:

    #
    # Neuinstallation: dann weiter "XRack".
    #
    assert ap_vorgabe(Path(tmp), None) == "XRack", (
        "Ohne eingerichteten Access Point muss 'XRack' die Vorgabe bleiben."
    )

    #
    # Und eine Datei ohne SSID-Zeile darf nichts Halbes liefern.
    #
    assert ap_vorgabe(Path(tmp), "interface=wlan1\ncountry_code=DE\n") == "XRack", (
        "Ohne ssid-Zeile muss die Vorgabe greifen."
    )

    print("OK: Ohne eingerichteten Access Point bleibt es bei 'XRack'")


with tempfile.TemporaryDirectory() as tmp:

    #
    # Ein Name mit Leerzeichen und Gleichheitszeichen - beides ist in
    # einer SSID erlaubt und beides bringt naives Zerlegen aus dem
    # Tritt.
    #
    assert ap_vorgabe(Path(tmp), "ssid=Bus 7 = laut\nwpa_passphrase=x\n") \
        == "Bus 7 = laut", "Eine SSID mit Leer- und Gleichheitszeichen wird verstümmelt."

    print("OK: Auch eine SSID mit Sonderzeichen kommt vollständig an")


print("Alle Installer-Einstellungstests erfolgreich.")
