#!/usr/bin/env python3
"""
Netzwerk-Selbsttest.

Zwei Dinge muss er koennen, und beide sind hier festgehalten:

  1. Auch dann etwas liefern, wenn Teile fehlen. Ein Selbsttest, der
     genau bei einem kaputten Netz abstuerzt, ist wertlos.
  2. Im Befund benennen, was nicht zusammenpasst - das ist der Teil,
     der die Arbeit spart. Eine reine Bestandsaufnahme haette der
     Nutzer auch von Hand zusammensuchen koennen.
"""

import logging
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path

from core.network_report import NetworkReport


def funkbaum(wurzel: Path, geraete: dict) -> Path:
    """Stellt /sys/class/net nach. Name -> ("usb"|"platform", MAC)."""

    sysnet = wurzel / "sys" / "class" / "net"
    sysnet.mkdir(parents=True, exist_ok=True)

    for name, (art, mac) in geraete.items():

        geraet = sysnet / name
        geraet.mkdir()
        (geraet / "wireless").mkdir()
        (geraet / "address").write_text(f"{mac}\n")

        ziel = wurzel / ("bus/usb/devices/1-1" if art == "usb"
                         else "devices/platform/soc/mmc")
        ziel.mkdir(parents=True, exist_ok=True)
        (geraet / "device").symlink_to(ziel)

    return sysnet


def anwendung(wlan_status, host="192.168.1.50", kanaele=18, herkunft="discovered",
              gebrueckt=False, unit_soll="2"):
    """Attrappe der Anwendung - nur das, was der Bericht anfasst."""

    zeug = types.SimpleNamespace(
        config=types.SimpleNamespace(
            data=types.SimpleNamespace(
                application=types.SimpleNamespace(version="1.8.2")
            )
        ),
        wlan_control=types.SimpleNamespace(
            get_status=lambda: wlan_status,
            console_port_bridged=lambda: gebrueckt,
            _erwartete_unit_version=lambda: unit_soll,
        ),
        logger=logging.getLogger("XRack-Test"),
    )

    zeug._console_host_and_channels = lambda: (host, kanaele, herkunft)

    return zeug


GESUND = {
    "available": True, "country": "DE",
    "ap_hardware": True, "ap_active": True, "ap_ssid": "XRack",
    "home_active": True, "home_ssid": "Heimnetz",
    "bridge_enabled": False, "console_access_enabled": True,
}


def bericht(app, sysnet, ap_konf, befehle=None):
    """Baut den Bericht mit abgefangenen Systemaufrufen."""

    r = NetworkReport(app, sys_net=sysnet)
    r.ap_konfiguration = lambda: ap_konf
    r._lauf = lambda befehl, timeout=10.0: (befehle or {}).get(befehl[0], "")

    return r


# ====================================================================
# Der gute Fall
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    wurzel = Path(tmp)
    sysnet = funkbaum(wurzel, {
        "wlan0": ("platform", "11:22:33:44:55:66"),
        "wlan1": ("usb", "aa:bb:cc:dd:ee:ff"),
    })

    ap_konf = {
        "interface": "wlan1", "country_code": "DE",
        "hw_mode": "a", "channel": "36", "unit_version": "2",
    }

    text = bericht(anwendung(GESUND), sysnet, ap_konf).erzeugen()

    for erwartet in ("Netzwerk-Selbsttest", "FUNKGERÄTE", "ACCESS POINT",
                     "MISCHPULT", "BEFUND", "1.8.2"):
        assert erwartet in text, f"'{erwartet}' fehlt:\n{text}"

    assert "wlan1    USB-Stick" in text, text
    assert "wlan0    eingebaut" in text, text
    assert "5 GHz, Kanal 36" in text, text

    assert "Nichts Auffälliges gefunden." in text, (
        "Bei stimmigem Zustand darf kein Befund erscheinen:\n" + text
    )

    #
    # Das WLAN-Passwort darf nirgends auftauchen - das Skript filtert
    # es heraus, und der Bericht wird weitergeschickt.
    #
    assert "wpa_passphrase" not in text and "passwort" not in text.lower(), text

    print("OK: Der Bericht steht, und bei stimmigem Zustand meldet er nichts")


# ====================================================================
# Der Befund erkennt, was nicht zusammenpasst
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    wurzel = Path(tmp)
    sysnet = funkbaum(wurzel, {
        "wlan0": ("usb", "aa:bb:cc:dd:ee:ff"),
        "wlan1": ("platform", "11:22:33:44:55:66"),
    })

    faelle = [
        (
            "Funkregion fehlt",
            {**GESUND, "country": None},
            {"interface": "wlan0", "hw_mode": "a", "unit_version": "2"},
            "Keine Funkregion gesetzt",
        ),
        (
            "Access Point auf dem eingebauten Chip",
            GESUND,
            {"interface": "wlan1", "hw_mode": "a", "unit_version": "2"},
            "das ist das eingebaute WLAN",
        ),
        (
            "2,4 GHz trotz Stick",
            GESUND,
            {"interface": "wlan0", "hw_mode": "g", "unit_version": "2"},
            "funkt auf 2,4 GHz",
        ),
        (
            "Unit veraltet",
            GESUND,
            {"interface": "wlan0", "hw_mode": "a", "unit_version": "1"},
            "Unit ist auf Stand 1",
        ),
        (
            "beide Zugangswege an",
            {**GESUND, "bridge_enabled": True, "console_access_enabled": True},
            {"interface": "wlan0", "hw_mode": "a", "unit_version": "2"},
            "schließen sich aus",
        ),
    ]

    for name, wlan, ap_konf, erwartet in faelle:

        text = bericht(anwendung(wlan), sysnet, ap_konf).erzeugen()

        assert erwartet in text, (
            f"Befund '{name}' wurde nicht gemeldet (gesucht: {erwartet!r}):\n"
            + text[text.index("BEFUND"):]
        )

        print(f"OK: Befund erkannt - {name}")


# ====================================================================
# Fehlende Teile duerfen den Bericht nicht kippen
#
# Genau dann wird er gebraucht: wenn etwas nicht da ist.
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    wurzel = Path(tmp)

    # Kein Funkgeraet, keine AP-Konfiguration, kein Pult, nichts.
    leer = wurzel / "sys" / "class" / "net"
    leer.mkdir(parents=True)

    kaputt = {
        "available": False, "country": None,
        "ap_hardware": False, "ap_active": False, "ap_ssid": None,
        "home_active": False, "home_ssid": None,
        "bridge_enabled": False, "console_access_enabled": False,
    }

    app = anwendung(kaputt, host=None, kanaele=0, herkunft="discovered",
                    gebrueckt=None)

    text = bericht(app, leer, {}).erzeugen()

    assert "keine gefunden" in text, text
    assert "nicht lesbar oder nicht eingerichtet" in text, text
    assert "keine Adresse - nicht gefunden" in text, text
    assert "nicht feststellbar" in text, text
    assert "BEFUND" in text, text

    print("OK: Ohne Funkgerät, ohne Access Point, ohne Pult kommt trotzdem "
          "ein Bericht")

    #
    # Und auch dann nicht, wenn das sudo-Skript gar nicht antwortet -
    # dafuer wird die echte ap_konfiguration() benutzt, deren Aufruf
    # ins Leere laeuft.
    #
    echt = NetworkReport(app, sys_net=leer)
    echt._lauf = lambda befehl, timeout=10.0: ""

    assert echt.ap_konfiguration() == {}, "Ein leerer Aufruf muss {} liefern"

    text = echt.erzeugen()
    assert "BEFUND" in text, text

    print("OK: Auch ein fehlgeschlagener sudo-Aufruf kippt den Bericht nicht")


# ====================================================================
# Nichtwissen darf nicht als Befund durchgehen
#
# Der Fall aus dem Betrieb: Der Access Point lief einwandfrei, aber
# scripts/xrack-net-ap.sh --report kam nicht an /etc/hostapd/xrack.conf
# heran. Zurueck kam nur die Unit-Marke - aus einer anderen Datei. Der
# Bericht meldete daraufhin "Funkgerät: ?", "Ländercode: nicht
# gesetzt" und darunter "Nichts Auffälliges gefunden". Beides war
# falsch, und das zweite war das schlimmere.
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    wurzel = Path(tmp)
    sysnet = funkbaum(wurzel, {
        "wlan0": ("platform", "11:22:33:44:55:66"),
        "wlan1": ("usb", "aa:bb:cc:dd:ee:ff"),
    })

    # Genau das, was der Pi geliefert hat: nur die Unit-Marke.
    text = bericht(anwendung(GESUND), sysnet, {"unit_version": "2"}).erzeugen()

    assert "nicht gesetzt" not in text, (
        "Ueber eine nicht gelesene Datei darf der Bericht nichts behaupten:\n"
        + text
    )
    assert "Funkgerät:" not in text, text
    assert "Konfiguration: nicht lesbar" in text, text

    # Die Unit-Marke kam ja durch, die gehoert weiter hin.
    assert "Unit-Stand:    2" in text, text

    befund = text[text.index("BEFUND"):]

    assert "Nichts Auffälliges gefunden." not in befund, (
        "Bei fehlenden Daten darf kein Freibrief erteilt werden:\n" + befund
    )
    assert "nicht gelesen werden" in befund, befund

    print("OK: Unlesbare AP-Konfiguration wird als solche gemeldet, nicht als "
          "'nicht gesetzt' und nicht als Entwarnung")

    #
    # Laeuft der Access Point gar nicht, ist eine fehlende
    # Konfiguration nichts Besonderes - dann darf der Befund auch
    # nicht meckern.
    #
    aus = {**GESUND, "ap_active": False, "ap_hardware": False}
    befund = bericht(anwendung(aus), sysnet, {}).erzeugen()
    befund = befund[befund.index("BEFUND"):]

    assert "nicht gelesen werden" not in befund, befund

    print("OK: Bei ausgeschaltetem Access Point bleibt der Befund still")

    #
    # Gelesen, aber ohne Ländercode: Das ist eine echte Aussage - und
    # der Grund, warum 5 GHz gesperrt bleibt.
    #
    text = bericht(anwendung(GESUND), sysnet,
                   {"interface": "wlan1", "hw_mode": "a",
                    "channel": "36", "unit_version": "2"}).erzeugen()

    assert "Ländercode:    nicht gesetzt" in text, text
    assert "kein Ländercode hinterlegt" in text, text

    print("OK: Fehlender Ländercode wird gemeldet, wenn er wirklich fehlt")


# ====================================================================
# Und das Skript dahinter: liefert es die Werte auch aus?
#
# Der eigentliche Fehler sass nicht in Python, sondern in
# scripts/xrack-net-ap.sh: Die --report-Verzweigung benutzte ${CONF},
# bevor die Variable gesetzt war. "[ -f "" ]" trifft nie zu, also kam
# aus der hostapd-Datei nichts zurueck, waehrend die systemd-Zeile
# durchkam - deren Pfad stand fest im Zweig. Deshalb wird hier das
# Skript selbst aufgerufen.
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    wurzel = Path(tmp)

    conf = wurzel / "xrack.conf"
    conf.write_text(
        "interface=wlan1\n"
        "bridge=br0\n"
        "ssid=XRack\n"
        "country_code=DE\n"
        "ieee80211d=1\n"
        "hw_mode=a\n"
        "channel=36\n"
        "wpa=2\n"
        "wpa_passphrase=streng-geheim-1234\n"
    )

    unit = wurzel / "xrack-hostapd.service"
    unit.write_text(
        "[Unit]\n"
        "# XRack-Unit-Version: 2\n"
        "Description=XRack Access Point\n"
    )

    umgebung = {
        **os.environ,
        "XRACK_HOSTAPD_CONF": str(conf),
        "XRACK_HOSTAPD_UNIT": str(unit),
    }

    lauf = subprocess.run(
        ["bash", str(Path("scripts/xrack-net-ap.sh").resolve()), "--report"],
        capture_output=True, text=True, env=umgebung, timeout=30,
    )

    assert lauf.returncode == 0, (lauf.returncode, lauf.stderr)

    ausgabe = lauf.stdout

    for erwartet in ("interface=wlan1", "country_code=DE", "hw_mode=a",
                     "channel=36", "# XRack-Unit-Version: 2"):
        assert erwartet in ausgabe, (
            f"'{erwartet}' fehlt in der Ausgabe von --report:\n{ausgabe}"
        )

    #
    # Und das Passwort bleibt drin. Die Datei wird gefiltert und nicht
    # durchgereicht - der Bericht landet spaeter in einer Textdatei
    # und womoeglich in einem Forum.
    #
    assert "wpa_passphrase" not in ausgabe and "streng-geheim" not in ausgabe, (
        "Das WLAN-Passwort darf den Selbsttest nicht verlassen:\n" + ausgabe
    )

    print("OK: xrack-net-ap.sh --report liefert die Werte - und nicht das "
          "Passwort")

    #
    # Der Weg von der Skriptausgabe in den Bericht, ohne Attrappe
    # dazwischen: ap_konfiguration() muss daraus die Werte lesen.
    #
    leer = wurzel / "sys" / "class" / "net"
    leer.mkdir(parents=True)

    echt = NetworkReport(anwendung(GESUND), sys_net=leer)
    echt._lauf = lambda befehl, timeout=10.0: ausgabe.strip()

    werte = echt.ap_konfiguration()

    assert werte.get("interface") == "wlan1", werte
    assert werte.get("country_code") == "DE", werte
    assert werte.get("channel") == "36", werte
    assert werte.get("unit_version") == "2", werte
    assert "wpa_passphrase" not in werte, werte

    print("OK: Der Bericht liest die Skriptausgabe richtig aus")


print("Alle Selbsttest-Tests erfolgreich.")
