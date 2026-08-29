#!/usr/bin/env python3
"""
Prüft das Modell hinter der Lichtsteuerung: Vorlagen, Lampen, Szenen
und die Umrechnung in ein DMX-Bild.

Hier ist alles reine Rechnung - kein Gerät, kein Dienst, keine
Datei außer der Ablage selbst. Deshalb lässt sich hier auch das
prüfen, was am Gerät am mühsamsten zu finden wäre: dass eine Lampe
genau an ihrer Adresse landet und nirgends sonst.
"""

import logging
import tempfile
import threading
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

#
# Eine Lampe mit eigenem Dimmerkanal: Der muss aufgedreht werden, auch
# wenn niemand an der Helligkeit gedreht hat. Sonst steht eine Farbe
# in den Kanaelen, der Dimmer aber auf 0 - und die Lampe bleibt
# dunkel, ohne dass man sieht, warum.
#
ausgabe = fixtures.bild(
    [{"id": "d", "name": "Par", "template": "rgb-dimmer", "address": 1}],
    VORLAGEN,
    {"d": [0, 255, 0, 0]},
)

assert ausgabe[0] == 255, (
    f"Der Dimmerkanal muss ohne Zutun aufgedreht sein, steht aber auf "
    f"{ausgabe[0]}"
)
assert ausgabe[1:4] == [255, 0, 0], ausgabe[1:4]

#
# Und mit halber Helligkeit wird der Dimmer gesetzt, nicht die Farbe.
#
ausgabe = fixtures.bild(
    [{"id": "d", "name": "Par", "template": "rgb-dimmer", "address": 1}],
    VORLAGEN,
    {"d": [0, 255, 0, 0]},
    {"d": 128},
)

assert ausgabe[0] == 128 and ausgabe[1] == 255, ausgabe[0:4]

print("OK: Lampen mit Dimmerkanal gehen an, ohne dass jemand dreht")


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
        self.light_brightness = {}
        self._light_lock = threading.Lock()
        self.logger = logging.getLogger("XRack-Test")

        #
        # Der Show-Motor haengt am Statusbericht, also gehoert er auch
        # in die Attrappe - sonst prueft man eine Anwendung, die es so
        # gar nicht gibt.
        #
        from lighting.light_engine import LightEngine

        self.light_engine = LightEngine(self)


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
    # Und jetzt der Punkt, an dem die erste Fassung falsch war:
    # Dimmen rechnet Farbwerte herunter, und das ist nicht umkehrbar.
    # Wurde die Helligkeit in die gemerkten Werte hineingerechnet,
    # blieb nach einmal Herunterziehen und Hochziehen dauerhaft die
    # halbe Farbe stehen. Die gemerkten Werte muessen ungedimmt
    # bleiben.
    #
    assert app.light_values["bar"] == [200, 100, 50], (
        "Die gemerkten Werte duerfen vom Dimmen nicht angefasst werden: "
        + str(app.light_values["bar"])
    )

    app.set_light_fixture_brightness("bar", 255)

    assert dmx.gesendet[-1][9:12] == [200, 100, 50], (
        "Nach dem Hochziehen muss wieder die volle Farbe stehen: "
        + str(dmx.gesendet[-1][9:12])
    )

    print("OK: Herunterdimmen und wieder hochziehen stellt die Farbe her")

    #
    # Und die Oberflaeche muss den eingestellten Wert wiederfinden -
    # sonst springt der Regler beim naechsten Aufbau der Karte zurueck
    # auf voll. Genau das war am Geraet zu sehen.
    #
    app.set_light_fixture_brightness("bar", 64)

    assert app.get_lighting_status()["brightness"]["bar"] == 64, (
        "Der eingestellte Helligkeitswert muss im Status stehen."
    )

    app.set_light_fixture_brightness("bar", 255)

    print("OK: Die eingestellte Helligkeit steht im Status")

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
    # Die Helligkeit gehoert zur Szene. Ohne sie kaeme eine gedaempfte
    # Stimmung beim Aufrufen mit voller Helligkeit zurueck.
    #
    app.set_light_fixture_values("bar", [0, 255, 0])
    app.set_light_fixture_brightness("bar", 51)

    erfolg, meldung = app.save_light_scene("Gedaempft")
    assert erfolg, meldung

    app.set_light_fixture_brightness("bar", 255)
    assert dmx.gesendet[-1][9:12] == [0, 255, 0]

    gedaempft = [s for s in app.lighting_store.szenen() if s["name"] == "Gedaempft"][0]

    app.activate_light_scene(gedaempft["id"])

    assert dmx.gesendet[-1][9:12] == [0, 51, 0], (
        "Die Szene muss mit ihrer Helligkeit zurueckkommen: "
        + str(dmx.gesendet[-1][9:12])
    )

    print("OK: Eine Szene merkt sich auch die Helligkeit")

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


# ====================================================================
# 9. Die musikgesteuerte Show: aus drei Zahlen wird ein Lichtbild
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    licht = ablage(Path(tmp))
    licht.set_enabled(True)
    licht.lampe_speichern({
        "id": "bar", "name": "LED-Bar", "template": "bar-8-rgb", "address": 1,
    })

    dmx = DmxAttrappe()
    app = LichtApp(licht, dmx)

    motor = app.light_engine

    #
    # Dieselbe Segmentbildung wie in der Oberflaeche: aus 24 Kanaelen
    # acht Segmente. Laufen die beiden auseinander, zeigt die Karte
    # etwas anderes an, als die Show ansteuert.
    #
    gruppen = motor._gruppen(["red", "green", "blue"] * 8)

    assert len(gruppen) == 8, len(gruppen)
    assert all(len(g) == 3 for g in gruppen), gruppen

    print("OK: Die Show teilt die Kanäle genauso in Segmente wie die Karte")

    #
    # Bass laut, Hoehen leise -> Rot deutlich ueber Blau.
    #
    motor.stand = {"low": 1.0, "mid": 0.5, "high": 0.0, "level": 0.5, "beat": False}
    motor.position = 0

    werte = motor.werte_je_lampe()["bar"]

    assert werte[0] > 200, f"Rot muss bei vollem Bass hoch sein: {werte[:3]}"
    assert werte[2] == 0, f"Blau muss bei fehlenden Hoehen aus sein: {werte[:3]}"
    assert werte[1] > 0, werte[:3]

    print("OK: Bass wird zu Rot, Höhen zu Blau")

    #
    # Der wandernde Punkt: Segment 0 ist dran und muss heller sein als
    # die uebrigen.
    #
    assert werte[0] > werte[3], (
        f"Das Segment, das dran ist, muss heller leuchten: {werte[0]} vs {werte[3]}"
    )

    motor.position = 3
    werte = motor.werte_je_lampe()["bar"]

    assert werte[9] > werte[0], (
        "Nach dem Weiterruecken muss ein anderes Segment vorn sein."
    )

    print("OK: Der helle Punkt wandert über die Segmente")

    #
    # Ohne Signal bleibt es dunkel - kein Grundleuchten, das man
    # nachher nicht mehr los wird.
    #
    motor.stand = {"low": 0.0, "mid": 0.0, "high": 0.0, "level": 0.0, "beat": False}

    assert set(motor.werte_je_lampe()["bar"]) == {0}, motor.werte_je_lampe()["bar"]

    print("OK: Ohne Signal bleibt die Show dunkel")


# --- Bewegtlicht: Position ja, Blitzlicht nein ----------------------

with tempfile.TemporaryDirectory() as tmp:

    licht = ablage(Path(tmp))
    licht.set_enabled(True)
    licht.vorlage_speichern({
        "id": "kopf", "name": "Kopf",
        "channels": ["pan", "tilt", "red", "green", "blue", "strobe"],
    })
    licht.lampe_speichern({
        "id": "k", "name": "Kopf", "template": "kopf", "address": 1,
    })

    app = LichtApp(licht, DmxAttrappe())
    motor = app.light_engine

    motor.stand = {"low": 1.0, "mid": 0.5, "high": 0.2, "level": 0.5, "beat": False}
    motor.phase = 1.0

    werte = motor.werte_je_lampe()["k"]

    assert werte[0] > 0 and werte[1] > 0, f"Pan/Tilt muessen bewegt werden: {werte}"

    #
    # Und das Wichtigste: Der Strobe-Kanal bleibt aus. Ein Blitzlicht,
    # das von selbst angeht, ist auf einer Buehne keine Ueberraschung,
    # die jemand haben will.
    #
    assert werte[5] == 0, f"Strobe darf die Show nicht von selbst ausloesen: {werte}"

    print("OK: Bewegtlicht wird geschwenkt - aber das Blitzlicht bleibt aus")


# --- Der Rückfall bei Sprache und Stille ----------------------------

with tempfile.TemporaryDirectory() as tmp:

    licht = ablage(Path(tmp))
    licht.set_enabled(True)
    licht.lampe_speichern({
        "id": "bar", "name": "LED-Bar", "template": "rgb", "address": 1,
    })

    dmx = DmxAttrappe()
    app = LichtApp(licht, dmx)

    #
    # Ohne hinterlegte Szene: Licht aus. Das ist die ehrlichere
    # Vorgabe - Licht, das bei einer Ansage weiterzuckt, ist
    # schlimmer als Dunkelheit.
    #
    app.light_values = {"bar": [255, 255, 255]}
    dmx.gesendet.clear()

    app.licht_rueckfall("speech")

    assert set(dmx.gesendet[-1]) == {0}, dmx.gesendet[-1][:6]

    print("OK: Ohne Rückfallszene geht das Licht bei einer Ansage aus")

    #
    # Mit Szene: genau diese Szene.
    #
    app.set_light_fixture_values("bar", [0, 0, 255])
    app.save_light_scene("Pause")

    szenen_id = licht.szenen()[0]["id"]

    ok, meldung = licht.set_show_einstellungen({"fallback_scene": szenen_id})
    assert ok, meldung

    app.set_light_fixture_values("bar", [255, 0, 0])
    app.licht_rueckfall("silence")

    assert dmx.gesendet[-1][0:3] == [0, 0, 255], dmx.gesendet[-1][0:3]

    print("OK: Mit Rückfallszene wird genau diese aufgerufen")

    #
    # Eine Szene, die es nicht gibt, wird abgewiesen - sonst passierte
    # bei Stille einfach nichts, und niemand wuesste warum.
    #
    ok, meldung = licht.set_show_einstellungen({"fallback_scene": "gibtsnicht"})

    assert not ok and "gibt es nicht" in meldung, meldung

    print("OK: Eine nicht vorhandene Rückfallszene wird abgewiesen")


# --- Die Warteschlange darf den Lesethread nie aufhalten ------------

with tempfile.TemporaryDirectory() as tmp:

    licht = ablage(Path(tmp))
    licht.set_enabled(True)

    app = LichtApp(licht, DmxAttrappe())
    motor = app.light_engine

    motor._laeuft = True   # ohne Thread: die Warteschlange laeuft voll

    for _ in range(50):
        motor.block_empfangen(b"\x00" * 64)

    assert motor.verworfen > 0, (
        "Bei voller Warteschlange muss verworfen werden, nicht gewartet."
    )

    motor._laeuft = False

    print(f"OK: Volle Warteschlange verwirft ({motor.verworfen} Blöcke), "
          f"statt den Lesethread aufzuhalten")


# --- Die Stille-Schwelle muss zu echten Pegeln passen ---------------
#
# Am Geraet: Die Show schaltete bei laufender Musik auf die
# Rueckfallszene, weil die Schwelle bei 0.02 lag - das sind -34 dBFS.
# Ein normaler Ausspielweg vom Pult liegt weit darunter; erst mit dem
# Kanal auf 0 dB kam das Signal darueber.
#
# Die Zusicherung ist bewusst grosszuegig: Es geht nicht um einen
# bestimmten Wert, sondern darum, dass die Vorgabe im Bereich eines
# Rauschteppichs liegt und nicht im Bereich normaler Musik.

import math

from lighting.store import SHOW_VORGABE

schwelle_db = 20 * math.log10(SHOW_VORGABE["silence_threshold"])

assert schwelle_db <= -46, (
    f"Die Stille-Schwelle liegt bei {schwelle_db:.0f} dBFS - damit haelt die "
    f"Show einen normal ausgesteuerten Ausspielweg fuer Stille."
)

#
# Und nicht so tief, dass sie nie greift: Rauschen und Brummen sollen
# noch als Stille durchgehen.
#
assert schwelle_db >= -70, (
    f"Die Stille-Schwelle liegt bei {schwelle_db:.0f} dBFS - so tief greift "
    f"sie bei einem rauschenden Eingang nie."
)

print(f"OK: Die Stille-Schwelle liegt bei {schwelle_db:.0f} dBFS - "
      f"unter normaler Musik, über dem Rauschen")


# --- Die Farben der Bänder sind einstellbar -------------------------
#
# Fruehr war tief=rot, mittel=gruen, hoch=blau fest verdrahtet. Das
# ist eine brauchbare Vorgabe, aber Geschmack und nicht Physik.

with tempfile.TemporaryDirectory() as tmp:

    licht = ablage(Path(tmp))
    licht.set_enabled(True)
    licht.lampe_speichern({
        "id": "par", "name": "Par", "template": "rgb", "address": 1,
    })

    app = LichtApp(licht, DmxAttrappe())
    motor = app.light_engine

    #
    # Nur tiefe Toene, Farbe dafuer auf Orange gestellt: Das braucht
    # Rot UND Gruen. Mit der alten, starren Zuordnung Band->Kanal
    # waere das gar nicht darstellbar gewesen.
    #
    motor.einstellungen = {
        "sensitivity": 1.0,
        "color_low": "#ff8000",
        "color_mid": "#000000",
        "color_high": "#000000",
    }

    motor.stand = {"low": 1.0, "mid": 0.0, "high": 0.0, "level": 0.5, "beat": False}

    werte = motor.werte_je_lampe()["par"]

    assert werte[0] == 255, f"Rotanteil von Orange fehlt: {werte}"
    assert 100 < werte[1] < 160, f"Grünanteil von Orange fehlt: {werte}"
    assert werte[2] == 0, f"Blau darf hier nicht leuchten: {werte}"

    print("OK: Ein Band kann jede Farbe bekommen, nicht nur Rot/Grün/Blau")

    #
    # Und die Baender mischen sich: tief blau + hoch rot, beide halb.
    #
    motor.einstellungen = {
        "sensitivity": 1.0,
        "color_low": "#0000ff",
        "color_mid": "#000000",
        "color_high": "#ff0000",
    }

    motor.stand = {"low": 0.5, "mid": 0.0, "high": 0.5, "level": 0.5, "beat": False}

    werte = motor.werte_je_lampe()["par"]

    assert 100 < werte[0] < 160, f"Rot aus dem Hoehenband fehlt: {werte}"
    assert 100 < werte[2] < 160, f"Blau aus dem Bassband fehlt: {werte}"

    print("OK: Die Bänder mischen sich zu einer Farbe")

    #
    # Unsinnige Farben werden schon beim Speichern abgewiesen - sonst
    # landet der Unsinn in einer Rechnung und faerbt entweder gar
    # nichts oder alles falsch.
    #
    ok, meldung = licht.set_show_einstellungen({"color_low": "rot"})
    assert not ok and "Farbe" in meldung, meldung

    ok, meldung = licht.set_show_einstellungen({"color_low": "#ff0000"})
    assert ok, meldung

    print("OK: Unsinnige Farbangaben werden abgewiesen")

    #
    # Und ohne jede Farbeinstellung - etwa bei einer Einrichtung aus
    # einer aelteren Fassung - muss die Vorgabe greifen. Ein fehlender
    # Wert darf nicht "kein Licht" bedeuten.
    #
    motor.einstellungen = {}
    motor.stand = {"low": 1.0, "mid": 0.0, "high": 0.0, "level": 0.5, "beat": False}

    werte = motor.werte_je_lampe()["par"]

    assert werte[0] > 200, (
        f"Ohne gespeicherte Farben muss die Vorgabe greifen: {werte}"
    )

    print("OK: Fehlen die Farben in der Ablage, greift die Vorgabe")




# ====================================================================
# 9. Die mitgelieferten Eurolite-Vorlagen
#
# Bei einer Vorlage aus einem Handbuch ist die Kanalzahl kein Detail:
# Steht sie falsch, ruecken alle folgenden Lampen im Universum um
# genau diesen Fehler, und was leuchtet, hat mit dem Gewollten nichts
# mehr zu tun. Deshalb wird hier Kanal fuer Kanal gegen die Tabelle
# aus dem Handbuch geprueft.
# ====================================================================

eingebaut = {v["id"]: v for v in fixtures.eingebaute_vorlagen()}

kls = eingebaut["eurolite-kls-180-21"]

assert len(kls["channels"]) == 21, len(kls["channels"])

# Handbuch Seite 16: 1 Dimmer, 2 Strobe-Tempo, 3 interne Programme,
# 4 Strobe Weiss, 5-20 vier Spots RGBW, 21 Programme ueber DMX.
assert kls["channels"][:4] == ["dimmer", "strobe", "generic", "strobe"]
assert kls["channels"][4:8] == ["red", "green", "blue", "white"]
assert kls["channels"][16:20] == ["red", "green", "blue", "white"]
assert kls["channels"][20] == "generic"

bar = eingebaut["eurolite-kls-laser-bar-pro-fx-28"]

assert len(bar["channels"]) == 28, len(bar["channels"])

# Handbuch Seite 19: vier Farbeinheiten zu je 5 Kanaelen, dann
# Laser/Laser/Rotation, dann fuenf Strobe-LED-Kanaele.
for start in (0, 5, 10, 15):
    assert bar["channels"][start:start + 4] == [
        "red", "green", "blue", "strobe",
    ], (start, bar["channels"][start:start + 5])

assert bar["channels"][4] == "rotation"
assert bar["channels"][19] == "rotation"
assert bar["channels"][20:23] == ["laser", "laser", "rotation"]
assert bar["channels"][23:] == ["shutter"] * 5

#
# Die KLS-180/6 hat sechs Spots statt vier und eigene Modi. Der
# 24-Kanal-Modus ist reine Farbe, der 29er hat davor Dimmer und
# Strobe und dahinter die Bar- und Programmkanaele.
#
sechs = eingebaut["eurolite-kls-180-6-24"]

assert len(sechs["channels"]) == 24, len(sechs["channels"])
assert sechs["channels"] == ["red", "green", "blue", "white"] * 6

sechs29 = eingebaut["eurolite-kls-180-6-29"]

assert len(sechs29["channels"]) == 29, len(sechs29["channels"])
assert sechs29["channels"][:2] == ["dimmer", "strobe"]
assert sechs29["channels"][2:26] == ["red", "green", "blue", "white"] * 6
assert sechs29["channels"][26:] == ["strobe", "generic", "generic"]

for vorlage in (kls, bar, sechs, sechs29):
    assert fixtures.pruefe_vorlage(vorlage) == "", vorlage["name"]

print("OK: Die Eurolite-Vorlagen stimmen mit den Handbüchern überein")


with tempfile.TemporaryDirectory() as tmp:

    licht = ablage(Path(tmp))
    licht.set_enabled(True)

    licht.lampe_speichern({
        "id": "kls", "name": "KLS", "template": "eurolite-kls-180-21",
        "address": 1,
    })
    licht.lampe_speichern({
        "id": "laser", "name": "Laser-Bar",
        "template": "eurolite-kls-laser-bar-pro-fx-28", "address": 30,
    })
    licht.lampe_speichern({
        "id": "sechs", "name": "KLS-180/6",
        "template": "eurolite-kls-180-6-24", "address": 70,
    })
    licht.lampe_speichern({
        "id": "sechs29", "name": "KLS-180/6 gross",
        "template": "eurolite-kls-180-6-29", "address": 100,
    })

    app = LichtApp(licht, DmxAttrappe())
    motor = app.light_engine

    motor.einstellungen = {"sensitivity": 1.0}
    motor.stand = {"low": 1.0, "mid": 1.0, "high": 1.0,
                   "level": 0.9, "beat": False}

    #
    # Was die Show unter keinen Umstaenden anfassen darf.
    #
    # Laser sind kein Geschmacksthema, sondern eine Gefahr; die
    # Programmkanaele wuerden das Geraet sein eigenes Ding machen
    # lassen und alles uebersteuern, was XRack sendet. Beides muss
    # ueber jede Position des Lauflichts hinweg auf 0 bleiben.
    #
    for schritt in range(20):

        motor.position = schritt
        werte = motor.werte_je_lampe()

        k = werte["kls"]
        b = werte["laser"]

        assert k[2] == 0, f"Interne Programme angesteuert: {k[2]}"
        assert k[20] == 0, f"Programme über DMX angesteuert: {k[20]}"
        assert k[1] == 0 and k[3] == 0, "Strobe angesteuert"

        assert b[20] == 0 and b[21] == 0, f"Laser angesteuert: {b[20:22]}"
        assert b[4] == 0 and b[19] == 0 and b[22] == 0, "Rotation angesteuert"
        assert b[23:] == [0] * 5, f"Strobe-LEDs angesteuert: {b[23:]}"

        s = werte["sechs29"]

        assert s[1] == 0 and s[26] == 0, "Strobe angesteuert"
        assert s[27] == 0 and s[28] == 0, (
            f"Bar- oder Programmkanal angesteuert: {s[27:]}"
        )

    print("OK: Laser, Strobe und Programmkanäle bleiben unangetastet")

    #
    # Und der wandernde Punkt muss in JEDEM Takt auf einer Gruppe
    # stehen, die auch leuchten kann.
    #
    # Bei der Laser-Bar sind fuenf der neun Gruppen reine
    # Laser-/Strobe-/Rotationskanaele. Zaehlte das Lauflicht die mit,
    # saehe man in fuenf von neun Takten kein volles Segment - das
    # Licht wuerde scheinbar grundlos aussetzen.
    #
    for schritt in range(20):

        motor.position = schritt

        for kennung in ("kls", "laser", "sechs", "sechs29"):

            werte = motor.werte_je_lampe()[kennung]

            assert max(werte) > 200, (
                f"{kennung}, Takt {schritt}: kein Segment voll an - "
                f"das Lauflicht steht auf einer Gruppe ohne Farbe. {werte}"
            )

    print("OK: Das Lauflicht steht nie auf einer Gruppe ohne Farbkanäle")

    #
    # Der 29-Kanal-Modus ist genau deshalb da: Er hat einen
    # Master-Dimmer, und mit dem dimmt der Regler das Geraet
    # wirklich, statt die Farbwerte herunterzurechnen. Das ist kein
    # Schoenheitsfehler - heruntergerechnete Farben verlieren unten
    # herum ihre Mischung, ein Dimmerkanal nicht.
    #
    app.light_values = {"sechs29": motor.werte_je_lampe()["sechs29"]}

    farben_voll = list(app.light_values["sechs29"][2:26])

    ok, meldung = app.set_light_fixture_brightness("sechs29", 40)
    assert ok, meldung

    rahmen = app.dmx_control.gesendet[-1]

    # Adresse 100 -> Kanal 100 ist der Master-Dimmer (Index 99).
    assert rahmen[99] == 40, f"Master-Dimmer nicht gesetzt: {rahmen[99]}"

    assert rahmen[101:125] == farben_voll, (
        "Die Farben wurden heruntergerechnet, obwohl es einen "
        "Dimmerkanal gibt."
    )

    print("OK: Der 29-Kanal-Modus dimmt über den Master-Dimmer")


print("Alle Licht-Tests erfolgreich.")
