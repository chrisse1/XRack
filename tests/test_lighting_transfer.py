#!/usr/bin/env python3
"""
Prüft das Sichern und Einspielen der Lichteinrichtung.

Wer zwei XRacks betreibt, baut die ganze Einrichtung sonst zweimal
von Hand - Vorlagen, Lampen, Adressen, Szenen, Farben - und beim
nächsten Umbau wieder.

Zwei Dinge müssen dabei stimmen, und das zweite ist das wichtigere:

  1. Was mitgenommen wird, muss drüben genauso ankommen.
  2. Was NICHT mitgenommen werden darf, darf auch nicht mitkommen.
     WLAN-Daten, PIN, Gerätename und Pult-Adresse gehören zum Gerät.
     Und eine kaputte Datei darf die vorhandene Einrichtung nicht
     zerlegen: Erst prüfen, dann schreiben.
"""

#
# Der Suchpfad zur Projektwurzel - siehe tests/_wurzel.py. Muss VOR
# allen Importen aus XRack stehen.
#
from _wurzel import WURZEL  # noqa: F401,E402


import json
import sys
from pathlib import Path


from lighting.store import LightingStore  # noqa: E402


class Speicher:
    """Zustandsspeicher im Arbeitsspeicher."""

    def __init__(self):
        self.werte = {}

    def get(self, schluessel, vorgabe=None):
        return self.werte.get(schluessel, vorgabe)

    def set(self, schluessel, wert):
        self.werte[schluessel] = wert


def eingerichtet() -> LightingStore:
    """Ein XRack, an dem schon jemand gearbeitet hat."""

    licht = LightingStore(Speicher())

    licht.set_enabled(True)

    licht.vorlage_speichern({
        "id": "eigenbau",
        "name": "Eigenbau 4x RGB",
        "channels": ["red", "green", "blue"] * 4,
    })

    licht.lampe_speichern({
        "id": "bar", "name": "LED-Bar", "template": "eigenbau",
        "address": 1, "kind": "effect",
    })

    licht.lampe_speichern({
        "id": "wash", "name": "Wash hinten", "template": "rgb",
        "address": 20, "kind": "background",
    })

    licht.szene_speichern(
        "Pause",
        {"bar": [255, 0, 0] * 4, "wash": [0, 0, 255]},
        helligkeiten={"bar": 128, "wash": 200},
    )

    licht.set_show_einstellungen({
        "channel": 17,
        "channel_mono": True,
        "effect_mode": "pulse",
        "snare_strobe": True,
        "color_low": "#ff8800",
    })

    return licht


# ====================================================================
# 1. Was gesichert wurde, kommt drüben genauso an
# ====================================================================

hier = eingerichtet()

abbild = hier.exportieren()

#
# Die Datei muss durch eine Datei passen: Was sich nicht als JSON
# schreiben und wieder lesen lässt, hilft niemandem.
#
abbild = json.loads(json.dumps(abbild))

drueben = LightingStore(Speicher())

erfolg, meldung = drueben.importieren(abbild)

assert erfolg, meldung

assert drueben.exportieren() == abbild, (
    "Nach dem Einspielen steht drüben etwas anderes als hier."
)

#
# Und im Einzelnen, damit im Fehlerfall dasteht, WAS fehlt.
#
assert [lampe["name"] for lampe in drueben.lampen()] == [
    "LED-Bar", "Wash hinten",
], drueben.lampen()

assert "eigenbau" in drueben.vorlagen(), sorted(drueben.vorlagen())

assert [szene["name"] for szene in drueben.szenen()] == ["Pause"], (
    drueben.szenen()
)

szene = drueben.szenen()[0]

assert szene["values"]["bar"] == [255, 0, 0] * 4, szene
assert szene["brightness"]["wash"] == 200, szene

einstellungen = drueben.show_einstellungen()

assert einstellungen["channel"] == 17, einstellungen
assert einstellungen["channel_mono"] is True, einstellungen
assert einstellungen["effect_mode"] == "pulse", einstellungen
assert einstellungen["snare_strobe"] is True, einstellungen
assert einstellungen["color_low"] == "#ff8800", einstellungen

print("OK: Vorlagen, Lampen, Szenen und Show-Einstellungen kommen an")


# ====================================================================
# 2. Was am Gerät hängt, bleibt am Gerät
#
# Ein Import, der WLAN-Daten oder eine PIN mitbrächte, wäre ein
# Fehler mit Ansage: Man spielt die Einrichtung des Proberaum-Racks
# ein und hat plötzlich dessen Netz-Zugangsdaten.
# ====================================================================

speicher = Speicher()

speicher.set("mdns_alias", "xrack")
speicher.set("console_ip_manual", "192.168.1.77")
speicher.set("record_channels", 32)

licht = LightingStore(speicher)
licht.lampe_speichern({"id": "l", "name": "L", "template": "rgb", "address": 1})

roh = json.dumps(licht.exportieren())

for verboten in ("mdns_alias", "console_ip_manual", "192.168.1.77",
                 "pin_hash", "psk", "ssid", "record_channels"):

    assert verboten not in roh, (
        f"'{verboten}' steht in der gesicherten Datei - dort gehört nichts "
        f"Gerätegebundenes hinein:\n{roh}"
    )

print("OK: In der Sicherung steht nichts Gerätegebundenes")


#
# Auch andersherum: Eine Datei, die so etwas mitbringt, darf es nicht
# in die Ablage schaffen.
#
angereichert = json.loads(roh)
angereichert["console_ip_manual"] = "10.0.0.9"
angereichert["pin_hash"] = "geklaut"

ziel_speicher = Speicher()
ziel_speicher.set("console_ip_manual", "192.168.1.5")

ziel = LightingStore(ziel_speicher)

erfolg, meldung = ziel.importieren(angereichert)

assert erfolg, meldung

assert ziel_speicher.get("console_ip_manual") == "192.168.1.5", (
    "Der Import hat die Pult-Adresse dieses Geräts überschrieben."
)
assert ziel_speicher.get("pin_hash") is None, (
    "Der Import hat eine PIN mitgebracht."
)

print("OK: Fremde Zusätze in der Datei landen nicht in der Ablage")


# ====================================================================
# 3. Eine kaputte Datei zerlegt die vorhandene Einrichtung nicht
#
# Das ist der Fall, der zählt. Wer eine Datei einspielt und dabei
# seine eigene Einrichtung verliert, verliert sie doppelt: Die neue
# ist auch nicht da.
# ====================================================================

vorhanden = eingerichtet()

vorher = vorhanden.exportieren()

for beschreibung, kaputt in (
    (
        "Lampe ohne passende Vorlage",
        {**vorher, "fixtures": [
            {"id": "x", "name": "Murks", "template": "gibtsnicht",
             "address": 1, "kind": "effect"},
        ]},
    ),
    (
        "Lampe ohne Adresse",
        {**vorher, "fixtures": [
            {"id": "x", "name": "Murks", "template": "rgb",
             "address": 0, "kind": "effect"},
        ]},
    ),
    (
        "Vorlage ohne Kanäle",
        {**vorher, "templates": [
            {"id": "leer", "name": "Leer", "channels": []},
        ]},
    ),
    (
        "Szene ohne Namen",
        {**vorher, "scenes": [{"id": "s", "name": "   ", "values": {}}]},
    ),
    (
        "gar keine XRack-Datei",
        {"irgendwas": True},
    ),
):

    erfolg, meldung = vorhanden.importieren(kaputt)

    assert not erfolg, f"{beschreibung}: wurde eingespielt statt abgelehnt."

    assert meldung, f"{beschreibung}: abgelehnt, aber ohne Begründung."

    assert vorhanden.exportieren() == vorher, (
        f"{beschreibung}: Die vorhandene Einrichtung wurde beschädigt."
    )

print("OK: Kaputte Dateien werden begründet abgelehnt, ohne Schaden")


# ====================================================================
# 4. Eine Datei aus einer neueren Fassung wird nicht geraten
# ====================================================================

zukunft = {**vorher, "version": vorher["version"] + 5}

erfolg, meldung = vorhanden.importieren(zukunft)

assert not erfolg and "Update" in meldung, meldung

print("OK: Eine neuere Datei wird abgelehnt, nicht geraten")


# ====================================================================
# 5. Szenen zeigen nach dem Einspielen auf vorhandene Lampen
#
# Eine Szene, die auf eine Lampe zeigt, die es in der Datei gar nicht
# gibt, würde später ins Leere greifen.
# ====================================================================

mit_geist = json.loads(json.dumps(vorher))

mit_geist["scenes"][0]["values"]["gibtsnicht"] = [1, 2, 3]
mit_geist["scenes"][0]["brightness"]["gibtsnicht"] = 99

ziel = LightingStore(Speicher())

erfolg, meldung = ziel.importieren(mit_geist)

assert erfolg, meldung

szene = ziel.szenen()[0]

assert "gibtsnicht" not in szene["values"], szene
assert "gibtsnicht" not in szene["brightness"], szene
assert "bar" in szene["values"], szene

print("OK: Werte zu fehlenden Lampen werden beim Einspielen verworfen")


# ====================================================================
# 6. Der Ein-/Ausschalter bleibt am Gerät
#
# Ob an DIESEM Rack überhaupt Licht hängt, weiß die Datei nicht.
# ====================================================================

aus = LightingStore(Speicher())

assert aus.enabled is False

erfolg, _ = aus.importieren(vorher)

assert erfolg

assert aus.enabled is False, (
    "Der Import hat die Lichtsteuerung eingeschaltet - ob hier Lampen "
    "hängen, weiß er aber nicht."
)

print("OK: Der Ein-/Ausschalter bleibt, wie er am Gerät steht")


print("Alle Übertragungs-Tests erfolgreich.")
