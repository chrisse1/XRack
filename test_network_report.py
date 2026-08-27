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


print("Alle Selbsttest-Tests erfolgreich.")
