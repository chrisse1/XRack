#!/usr/bin/env python3
"""
Prüft das Modell hinter der Lichtsteuerung: Vorlagen, Lampen, Szenen
und die Umrechnung in ein DMX-Bild.

Hier ist alles reine Rechnung - kein Gerät, kein Dienst, keine
Datei außer der Ablage selbst. Deshalb lässt sich hier auch das
prüfen, was am Gerät am mühsamsten zu finden wäre: dass eine Lampe
genau an ihrer Adresse landet und nirgends sonst.
"""

import tempfile
from pathlib import Path

from core.state_store import StateStore
from lighting import fixtures
from lighting.store import LightingStore


def ablage(ordner: Path) -> LightingStore:
    """Eine frische Ablage auf einer echten Datei."""

    return LightingStore(StateStore(ordner / "state.json"))


# ====================================================================
# 1. Vorlagen prüfen
# ====================================================================

assert fixtures.pruefe_vorlage({
    "id": "x", "name": "Test", "channels": ["red", "green", "blue"],
}) == "", "Eine gültige Vorlage wurde abgewiesen."

assert "Rolle" in fixtures.pruefe_vorlage({
    "id": "x", "name": "Test", "channels": ["red", "lila"],
}), "Eine erfundene Kanalrolle muss auffallen."

assert "mindestens einen Kanal" in fixtures.pruefe_vorlage({
    "id": "x", "name": "Test", "channels": [],
})

assert "Namen" in fixtures.pruefe_vorlage({
    "id": "x", "name": "   ", "channels": ["red"],
})

print("OK: Vorlagen werden geprüft, bevor sie in die Ablage kommen")


# ====================================================================
# 2. Lampen prüfen - vor allem der Rand des Universums
# ====================================================================

VORLAGEN = {
    vorlage["id"]: vorlage for vorlage in fixtures.eingebaute_vorlagen()
}

assert fixtures.pruefe_lampe(
    {"name": "Bar", "template": "bar-8-rgb", "address": 1}, VORLAGEN
) == ""

#
# Eine 24-Kanal-Lampe ab Adresse 489 endet genau auf 512 - das passt
# noch. Ab 490 nicht mehr. Genau dieser Rand ist der Fall, den man
# sonst erst auf der Bühne merkt.
#
assert fixtures.pruefe_lampe(
    {"name": "Bar", "template": "bar-8-rgb", "address": 489}, VORLAGEN
) == "", "Eine Lampe, die genau auf Kanal 512 endet, muss erlaubt sein."

fehler = fixtures.pruefe_lampe(
    {"name": "Bar", "template": "bar-8-rgb", "address": 490}, VORLAGEN
)

assert "512" in fehler, fehler

assert "Startadresse" in fixtures.pruefe_lampe(
    {"name": "Bar", "template": "rgb", "address": 0}, VORLAGEN
)

assert "keine Vorlage" in fixtures.pruefe_lampe(
    {"name": "Bar", "template": "gibtsnicht", "address": 1}, VORLAGEN
)

print("OK: Lampen werden geprüft, auch am Rand des Universums")


# ====================================================================
# 3. Überschneidungen
#
# Kein Fehler - aber die häufigste Ursache dafür, dass eine Lampe
# tut, was eine andere tun sollte.
# ====================================================================

#
# Die Bar belegt 1-24, danach ist Platz.
#
lampen = [
    {"id": "a", "name": "Bar",   "template": "bar-8-rgb", "address": 1},
    {"id": "b", "name": "Par 1", "template": "rgb",       "address": 25},
    {"id": "c", "name": "Par 2", "template": "rgb",       "address": 28},
]

assert fixtures.ueberschneidungen(lampen, VORLAGEN) == [], (
    "Lampen, die sich nicht überlappen, dürfen nicht gemeldet werden."
)

#
# Ein Kanal zu früh, und Par 1 sitzt auf dem letzten Kanal der Bar.
#
lampen[1]["address"] = 24

treffer = fixtures.ueberschneidungen(lampen, VORLAGEN)

assert ("a", "b") in treffer, treffer

print("OK: Überlappende Adressbereiche werden gefunden")


# ====================================================================
# 4. Dimmen - mit und ohne echten Dimmerkanal
# ====================================================================

mit_dimmer = VORLAGEN["rgb-dimmer"]
ohne_dimmer = VORLAGEN["rgb"]

#
# Mit Dimmerkanal: Der wird gesetzt, die Farbmischung bleibt, wie sie
# ist.
#
werte = fixtures.dimmen(mit_dimmer, [0, 200, 100, 50], 128)

assert werte == [128, 200, 100, 50], werte

print("OK: Mit Dimmerkanal wird der Dimmer gesetzt, nicht die Farbe")

#
# Ohne Dimmerkanal - der Fall der LED-Bar: Die Farben werden
# heruntergerechnet.
#
werte = fixtures.dimmen(ohne_dimmer, [200, 100, 50], 128)

assert werte == [100, 50, 25], werte

assert fixtures.dimmen(ohne_dimmer, [255, 255, 255], 0) == [0, 0, 0]
assert fixtures.dimmen(ohne_dimmer, [255, 255, 255], 255) == [255, 255, 255]

print("OK: Ohne Dimmerkanal wird die Farbe heruntergerechnet")

#
# Und was kein Farbkanal ist, wird dabei nicht angefasst: Ein
# heruntergedimmtes Bewegtlicht darf nicht die Position verlieren.
#
kopf = {
    "id": "k", "name": "Kopf",
    "channels": ["pan", "tilt", "red", "green", "blue", "strobe"],
}

werte = fixtures.dimmen(kopf, [200, 100, 200, 200, 200, 90], 128)

assert werte[0] == 200 and werte[1] == 100, (
    f"Pan/Tilt dürfen beim Dimmen nicht verändert werden: {werte}"
)
assert werte[5] == 90, f"Strobe darf beim Dimmen nicht verändert werden: {werte}"
assert werte[2:5] == [100, 100, 100], werte

print("OK: Beim Dimmen bleiben Position und Strobe unangetastet")


# ====================================================================
# 5. Das DMX-Bild
# ====================================================================

lampen = [
    {"id": "a", "name": "Bar", "template": "rgb", "address": 1},
    {"id": "b", "name": "Par", "template": "rgb", "address": 10},
]

ausgabe = fixtures.bild(lampen, VORLAGEN, {
    "a": [255, 0, 0],
    "b": [0, 0, 255],
})

assert len(ausgabe) == fixtures.DMX_KANAELE, len(ausgabe)

assert ausgabe[0:3] == [255, 0, 0], ausgabe[0:3]
assert ausgabe[9:12] == [0, 0, 255], ausgabe[9:12]

#
# Alles dazwischen und danach muss 0 sein. Sonst leuchtet irgendwo
# etwas, das niemand eingerichtet hat.
#
assert set(ausgabe[3:9]) == {0}, ausgabe[3:9]
assert set(ausgabe[12:]) == {0}

print("OK: Jede Lampe landet genau an ihrer Adresse und nirgends sonst")

#
# Eine Lampe ohne Zustand bleibt dunkel, und eine unbrauchbare Lampe
# (Vorlage weg) kippt das Bild nicht.
#
ausgabe = fixtures.bild(
    lampen + [{"id": "c", "name": "Kaputt", "template": "weg", "address": 5}],
    VORLAGEN,
    {"a": [255, 255, 255]},
)

assert ausgabe[0:3] == [255, 255, 255]
assert ausgabe[9:12] == [0, 0, 0], "Eine Lampe ohne Zustand muss dunkel bleiben."

print("OK: Fehlende Zustände und kaputte Lampen kippen das Bild nicht")


# ====================================================================
# 6. Die Ablage
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    licht = ablage(Path(tmp))

    assert licht.enabled is False, "Licht muss standardmäßig aus sein."

    licht.set_enabled(True)
    assert licht.enabled is True

    #
    # Die mitgelieferten Vorlagen sind ohne Zutun da.
    #
    vorlagen = licht.vorlagen()

    assert "bar-8-rgb" in vorlagen, sorted(vorlagen)
    assert len(vorlagen["bar-8-rgb"]["channels"]) == 24

    print("OK: Mitgelieferte Vorlagen sind sofort verfügbar")

    #
    # Eigene Vorlage - der Weg für Bewegtlichter, für die es bewusst
    # keine geratene Vorlage gibt.
    #
    ok, meldung = licht.vorlage_speichern({
        "id": "kopf",
        "name": "Bewegtlicht",
        "channels": ["pan", "tilt", "dimmer", "red", "green", "blue"],
    })

    assert ok, meldung
    assert "kopf" in licht.vorlagen()

    ok, meldung = licht.vorlage_speichern({
        "id": "murks", "name": "Murks", "channels": ["rot"],
    })

    assert not ok and "Rolle" in meldung, meldung

    print("OK: Eigene Vorlagen lassen sich anlegen, unsinnige nicht")

    #
    # Lampen
    #
    ok, meldung = licht.lampe_speichern({
        "id": "bar", "name": "LED-Bar", "template": "bar-8-rgb", "address": 1,
    })
    assert ok, meldung

    ok, meldung = licht.lampe_speichern({
        "name": "Zu weit", "template": "bar-8-rgb", "address": 500,
    })
    assert not ok and "512" in meldung, meldung

    assert len(licht.lampen()) == 1, licht.lampen()

    print("OK: Lampen werden nur angelegt, wenn sie ins Universum passen")

    #
    # Eine Vorlage, die benutzt wird, darf nicht verschwinden -
    # sonst stünde eine Lampe ohne Kanalbelegung da.
    #
    ok, meldung = licht.vorlage_loeschen("bar-8-rgb")
    assert not ok and "LED-Bar" in meldung, meldung

    print("OK: Eine benutzte Vorlage lässt sich nicht löschen")

    #
    # Szenen: gespeichert wird relativ zur Lampe.
    #
    ok, meldung, szenen_id = licht.szene_speichern("Pause", {
        "bar": [255, 0, 0] * 8,
        "gibtsnicht": [1, 2, 3],
    })

    assert ok, meldung

    szene = licht.szene(szenen_id)

    assert szene["name"] == "Pause"
    assert "gibtsnicht" not in szene["values"], (
        "Werte für unbekannte Lampen dürfen nicht abgelegt werden."
    )
    assert szene["values"]["bar"][:3] == [255, 0, 0]

    print("OK: Szenen speichern nur bekannte Lampen, relativ zu deren Adresse")

    #
    # Und der Punkt, für den das relativ gespeichert wird: Die Lampe
    # zieht auf eine andere Adresse um, die Szene stimmt weiterhin.
    #
    ok, meldung = licht.lampe_speichern({
        "id": "bar", "name": "LED-Bar", "template": "bar-8-rgb", "address": 100,
    })
    assert ok, meldung

    ausgabe = fixtures.bild(
        licht.lampen(), licht.vorlagen(), licht.szene(szenen_id)["values"]
    )

    assert ausgabe[99:102] == [255, 0, 0], ausgabe[99:102]
    assert set(ausgabe[0:99]) == {0}, "Auf der alten Adresse darf nichts stehen."

    print("OK: Nach einem Adresswechsel stimmen die Szenen weiterhin")

    #
    # Eine gelöschte Lampe verschwindet auch aus den Szenen.
    #
    ok, meldung = licht.lampe_loeschen("bar")
    assert ok, meldung

    assert licht.szene(szenen_id)["values"] == {}, (
        "Die Werte einer gelöschten Lampe dürfen nicht in den Szenen "
        "stehenbleiben: " + str(licht.szene(szenen_id)["values"])
    )

    print("OK: Eine gelöschte Lampe verschwindet auch aus den Szenen")


# ====================================================================
# 7. Übersteht das einen Neustart?
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    ordner = Path(tmp)

    licht = ablage(ordner)
    licht.set_enabled(True)
    licht.lampe_speichern({
        "id": "bar", "name": "LED-Bar", "template": "bar-8-rgb", "address": 5,
    })
    licht.szene_speichern("Blau", {"bar": [0, 0, 255] * 8})

    #
    # Frisch von der Platte gelesen, so wie nach einem Neustart.
    #
    wieder = ablage(ordner)

    assert wieder.enabled is True
    assert len(wieder.lampen()) == 1
    assert wieder.lampen()[0]["address"] == 5
    assert len(wieder.szenen()) == 1
    assert wieder.szenen()[0]["values"]["bar"][2] == 255

    print("OK: Die Einrichtung übersteht einen Neustart")


# ====================================================================
# 8. Die Anwendungsschicht
#
# Hier haengt zusammen, was einzeln schon geprueft ist: Ablage,
# Umrechnung und Ausgabe. Geprueft wird mit einem Attrappen-Dienst,
# der nur mitschreibt, was gesendet wuerde.
# ====================================================================

from core.application.licht import LichtMixin


class DmxAttrappe:
    """Merkt sich, was gesendet wurde. Optional stellt sie sich tot."""

    def __init__(self, antwortet: bool = True):

        self.gesendet = []
        self.antwortet = antwortet

    def send(self, werte):

        self.gesendet.append(list(werte))

        return self.antwortet

    def blackout(self):

        return self.send([0] * fixtures.DMX_KANAELE)

    def status(self):

        return {"service_running": self.antwortet, "adapter_present": True}


class LichtApp(LichtMixin):
    """Nur die Teile von Application, die die Lichtsteuerung anfasst."""

    def __init__(self, store, dmx):

        self.lighting_store = store
        self.dmx_control = dmx
        self.light_values = {}


def aufbau(ordner: Path, antwortet: bool = True):
    """Eine eingerichtete Anwendung mit einer Lampe auf Adresse 10."""

    licht = ablage(ordner)
    licht.set_enabled(True)
    licht.lampe_speichern({
        "id": "bar", "name": "LED-Bar", "template": "rgb", "address": 10,
    })

    dmx = DmxAttrappe(antwortet)

    return LichtApp(licht, dmx), dmx


with tempfile.TemporaryDirectory() as tmp:

    app, dmx = aufbau(Path(tmp))

    erfolg, meldung = app.set_light_fixture_values("bar", [255, 128, 0])

    assert erfolg, meldung
    assert dmx.gesendet, "Es wurde nichts an den Lichtdienst geschickt."
    assert dmx.gesendet[-1][9:12] == [255, 128, 0], dmx.gesendet[-1][9:12]

    print("OK: Werte einer Lampe landen an ihrer Adresse im gesendeten Bild")

    #
    # Zu viele Werte werden abgeschnitten, zu wenige aufgefuellt - ein
    # Fehler in der Oberflaeche darf nicht in die Nachbarlampe
    # hineinschreiben.
    #
    # Geprueft wird der gemerkte Zustand, nicht das gesendete Bild:
    # Dass nichts in die Nachbarlampe laeuft, verhindert schon bild()
    # (siehe oben). Wer hier auf das Bild schaut, prueft also die
    # falsche Stelle - die Zusicherung war beim ersten Anlauf genau
    # deshalb wirkungslos, die Gegenprobe blieb gruen. Was diese
    # Schicht zusichert, ist der saubere Zustand: Er geht so in jede
    # Szene, die von hier aus gespeichert wird.
    app.set_light_fixture_values("bar", [255] * 10)

    assert app.light_values["bar"] == [255, 255, 255], app.light_values["bar"]
    assert dmx.gesendet[-1][12] == 0, (
        "Zu viele Werte haben in den Kanal der naechsten Lampe geschrieben."
    )

    app.set_light_fixture_values("bar", [200])

    assert app.light_values["bar"] == [200, 0, 0], app.light_values["bar"]
    assert dmx.gesendet[-1][9:12] == [200, 0, 0], dmx.gesendet[-1][9:12]

    print("OK: Zu viele Werte werden gekappt, zu wenige aufgefüllt")

    #
    # Helligkeit bei einer Lampe ohne Dimmerkanal.
    #
    app.set_light_fixture_values("bar", [200, 100, 50])
    app.set_light_fixture_brightness("bar", 128)

    assert dmx.gesendet[-1][9:12] == [100, 50, 25], dmx.gesendet[-1][9:12]

    print("OK: Helligkeit wirkt auch ohne Dimmerkanal")

    #
    # Szene ablegen, etwas anderes einstellen, Szene zurueckholen.
    #
    app.set_light_fixture_values("bar", [0, 0, 255])

    erfolg, meldung = app.save_light_scene("Blau")
    assert erfolg, meldung

    app.set_light_fixture_values("bar", [255, 0, 0])
    assert dmx.gesendet[-1][9:12] == [255, 0, 0]

    szenen_id = app.lighting_store.szenen()[0]["id"]

    erfolg, meldung = app.activate_light_scene(szenen_id)

    assert erfolg, meldung
    assert dmx.gesendet[-1][9:12] == [0, 0, 255], dmx.gesendet[-1][9:12]

    print("OK: Eine Szene stellt den gespeicherten Stand wieder her")

    #
    # Blackout.
    #
    app.light_blackout()

    assert set(dmx.gesendet[-1]) == {0}, "Nach dem Blackout darf nichts stehen."

    print("OK: Blackout macht alles dunkel")

    #
    # Eine geloeschte Lampe geht aus - ihre alten Werte duerfen nicht
    # im Geraet stehenbleiben.
    #
    app.set_light_fixture_values("bar", [255, 255, 255])
    assert dmx.gesendet[-1][9:12] == [255, 255, 255]

    erfolg, meldung = app.delete_light_fixture("bar")

    assert erfolg, meldung
    assert set(dmx.gesendet[-1]) == {0}, (
        "Nach dem Löschen einer Lampe muss sie ausgehen: "
        + str(dmx.gesendet[-1][9:12])
    )

    print("OK: Eine gelöschte Lampe leuchtet nicht weiter")


# --- Aus heisst aus ------------------------------------------------

with tempfile.TemporaryDirectory() as tmp:

    app, dmx = aufbau(Path(tmp))

    app.set_light_fixture_values("bar", [255, 255, 255])

    #
    # Ausschalten muss das Licht mitnehmen. Sonst verschwaende die
    # Karte aus der Oberflaeche und die Lampen blieben an - niemand
    # kaeme mehr an sie heran.
    #
    dmx.gesendet.clear()

    erfolg, meldung = app.set_lighting_enabled(False)

    assert erfolg, meldung
    assert dmx.gesendet and set(dmx.gesendet[-1]) == {0}, (
        "Beim Ausschalten muss das Licht ausgehen."
    )
    assert app.light_values == {}, app.light_values

    #
    # Und danach wird nichts mehr gesendet.
    #
    dmx.gesendet.clear()

    app.set_light_fixture_values("bar", [255, 0, 0])

    assert dmx.gesendet == [], (
        "Bei ausgeschalteter Lichtsteuerung darf nichts gesendet werden."
    )

    print("OK: Ausgeschaltet bleibt es dunkel und still")


# --- Antwortet der Dienst nicht, faellt trotzdem nichts um ----------

with tempfile.TemporaryDirectory() as tmp:

    app, dmx = aufbau(Path(tmp), antwortet=False)

    erfolg, meldung = app.set_light_fixture_values("bar", [255, 0, 0])

    assert erfolg is False, "Ein toter Lichtdienst muss gemeldet werden."
    assert "olad" in meldung, meldung

    #
    # Die Einrichtung darf davon unberuehrt bleiben - der Nutzer soll
    # Lampen anlegen koennen, auch wenn das Kabel noch nicht steckt.
    #
    erfolg, meldung = app.save_light_fixture({
        "name": "Par", "template": "rgb", "address": 100,
    })

    assert erfolg, meldung
    assert len(app.lighting_store.lampen()) == 2

    print("OK: Ohne Lichtdienst wird gemeldet statt abgestürzt - und die "
          "Einrichtung geht weiter")


print("Alle Licht-Tests erfolgreich.")
