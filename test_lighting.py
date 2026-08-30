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


class RecorderAttrappe:
    """
    Nur so viel Recorder, wie die Lichtsteuerung liest.

    Die Kanalzahl des Interfaces steht im Statusbericht - die
    Oberfläche baut daraus die Auswahl des Kanalpaars.
    """

    class Backend:
        channels = 8
        rate = 48000

    backend = Backend()


class LichtApp(LichtMixin):
    """Nur die Teile von Application, die die Lichtsteuerung anfasst."""

    def __init__(self, store, dmx):

        self.lighting_store = store
        self.dmx_control = dmx
        self.recorder = RecorderAttrappe()
        self.light_values = {}
        self.light_brightness = {}

        #
        # Der Zustand der Blende - im Betrieb legt ihn
        # core/application/__init__.py an.
        #
        self._blende_von = {}
        self._blende_helligkeit_von = {}
        self._blende_ziel = {}
        self._blende_helligkeit_ziel = {}
        self._blende_dauer = 0.0
        self._blende_rest = 0.0
        self._show_uebernahme = False

        self._light_lock = threading.Lock()
        self.logger = logging.getLogger("XRack-Test")

        #
        # Der Show-Motor haengt am Statusbericht, also gehoert er auch
        # in die Attrappe - sonst prueft man eine Anwendung, die es so
        # gar nicht gibt.
        #
        from lighting.light_engine import LightEngine

        self.light_engine = LightEngine(self)


def blende_zuende(app, schritte: int = 400) -> None:
    """
    Die Blende in die Rueckfallszene zu Ende ziehen.

    Der Show-Thread tut das im Betrieb bei jedem Block. Wo es einem
    Test nur um das ZIEL geht und nicht um den Weg dorthin, steht
    dieser Helfer dafuer.
    """

    for _ in range(schritte):

        if app._blende_rest <= 0.0:
            return

        app.licht_rueckfall_halten(0.02)


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
    # Jedes Segment bekommt SEIN Band, nicht die Mischung aller drei.
    #
    # Vorher bekam jedes dieselbe gemischte Farbe. Bei Musik, in der
    # alle drei Baender vorkommen, ist diese Mischung mit Rot plus
    # Gruen plus Blau schlicht Weiss - am Geraet standen sechs weisse
    # Spots, die sich nur in der Helligkeit unterschieden.
    #
    motor.stand = {"low": 1.0, "mid": 0.5, "high": 0.0, "level": 0.5, "beat": False}
    motor.position = 0

    werte = motor.werte_je_lampe()["bar"]

    # Segment 1 haengt am Bass: nur Rot.
    assert werte[0] > 200, f"Segment 1 muss bei vollem Bass rot sein: {werte[0:3]}"
    assert werte[1] == 0 and werte[2] == 0, (
        f"Segment 1 darf nur Rot bekommen, nicht die Mischung: {werte[0:3]}"
    )

    # Segment 2 haengt an den Mitten: nur Gruen, und nur halb.
    assert 0 < werte[4] < 200, f"Segment 2 muss grün und halb sein: {werte[3:6]}"
    assert werte[3] == 0 and werte[5] == 0, (
        f"Segment 2 darf nur Grün bekommen: {werte[3:6]}"
    )

    # Segment 3 haengt an den Hoehen, und die fehlen: dunkel.
    assert werte[6:9] == [0, 0, 0], (
        f"Segment 3 muss bei fehlenden Höhen dunkel sein: {werte[6:9]}"
    )

    print("OK: Jedes Segment bekommt sein eigenes Frequenzband")

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
    blende_zuende(app)

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
    blende_zuende(app)

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
#
# Die fuenf weissen/UV-LEDs tragen die Rolle "strobe" - genau das
# sind sie. Vorher stand dort "shutter", damit die Show sie in Ruhe
# laesst; seit es den Blitz auf die Snare gibt, ist der Unterschied
# einer mit Wirkung: Angefasst werden sie nur, wenn er in den
# Einstellungen eingeschaltet ist.
#
assert bar["channels"][23:] == ["strobe"] * 5

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
    # Ein Blitzlicht, das von selbst angeht, will niemand; die
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

        assert b[3] == 0 and b[8] == 0, "Strobe angesteuert"
        assert b[23:] == [0] * 5, f"Strobe-LEDs angesteuert: {b[23:]}"

        s = werte["sechs29"]

        assert s[1] == 0 and s[26] == 0, "Strobe angesteuert"
        assert s[27] == 0 and s[28] == 0, (
            f"Bar- oder Programmkanal angesteuert: {s[27:]}"
        )

    print("OK: Strobe- und Programmkanäle bleiben unangetastet")


    #
    # Drehung und Laser dagegen fährt die Show mit.
    #
    # Die Werte sind nicht beliebig: Laut Handbuch steht ein
    # Drehkanal bei 0-4 still und laeuft erst ab 5 vorwaerts, in der
    # oberen Haelfte aber rueckwaerts. Ein Laser ist bei 0-4 aus,
    # bei 5-9 an, und ab 10 blitzt er. Landet ein Wert im falschen
    # Bereich, dreht der Derby rueckwaerts oder der Laser blitzt -
    # beides sieht man erst am Geraet, und beim Laser will man es
    # nicht sehen.
    #
    motor.stand = {"low": 1.0, "mid": 1.0, "high": 1.0,
                   "level": 0.9, "beat": False}

    b = motor.werte_je_lampe()["laser"]

    for kanal in (4, 19, 22):
        assert 5 <= b[kanal] <= 127, (
            f"Kanal {kanal + 1} dreht nicht vorwärts: {b[kanal]}"
        )

    for kanal in (20, 21):
        assert 5 <= b[kanal] <= 9, (
            f"Kanal {kanal + 1} ist kein sauberes \"Laser an\": {b[kanal]}"
        )

    print("OK: Drehung läuft vorwärts, die Laser stehen auf \"an\" statt Blitz")

    #
    # Bei Stille muessen die Laser aus sein - und die Drehung darf
    # trotzdem nicht stehenbleiben, sonst sieht der Derby kaputt aus.
    #
    motor.stand = {"low": 0.0, "mid": 0.0, "high": 0.0,
                   "level": 0.0, "beat": False}

    b = motor.werte_je_lampe()["laser"]

    assert b[20] == 0 and b[21] == 0, f"Laser bleibt an: {b[20:22]}"

    for kanal in (4, 19, 22):
        assert 5 <= b[kanal] <= 127, (
            f"Die Drehung bleibt stehen: Kanal {kanal + 1} = {b[kanal]}"
        )

    print("OK: Ohne Musik gehen die Laser aus, die Drehung läuft weiter")

    #
    # Und die beiden Laser haengen an verschiedenen Baendern - sonst
    # koennte man sie auch zusammenschalten.
    #
    motor.stand = {"low": 1.0, "mid": 0.0, "high": 0.0,
                   "level": 0.5, "beat": False}

    b = motor.werte_je_lampe()["laser"]

    assert b[20] > 0 and b[21] == 0, (
        f"Beide Laser hängen am selben Band: {b[20:22]}"
    )

    print("OK: Die beiden Laser hängen an verschiedenen Frequenzbändern")

    motor.stand = {"low": 1.0, "mid": 1.0, "high": 1.0,
                   "level": 0.9, "beat": False}

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

    #
    # Was die Show nicht faehrt, darf sie auch nicht loeschen.
    #
    # Bisher fing jedes Bild bei Null an. Da alle 20 ms eines kommt,
    # war ein von Hand gestellter Strobe- oder Laserkanal eine
    # Zwanzigstelsekunde spaeter wieder aus - von aussen sah es aus,
    # als taeten diese Regler ueberhaupt nichts.
    #
    app.light_values = {}
    app.light_brightness = {}

    vonHand = [0] * 28
    vonHand[3] = 90        # Strobe Derby 1
    vonHand[9] = 140       # "Keine Funktion" - Rolle generic
    vonHand[26] = 200      # weisse Strobe-LED 3

    ok, meldung = app.set_light_fixture_values("laser", vonHand)
    assert ok, meldung

    motor.position = 0

    for _ in range(5):
        app.licht_show_bild(motor.werte_je_lampe())

    stand29 = app.light_values["laser"]

    assert stand29[3] == 90, f"Strobe von der Show gelöscht: {stand29[3]}"
    assert stand29[9] == 140, f"Sonstiger Kanal gelöscht: {stand29[9]}"
    assert stand29[26] == 200, f"Strobe-LED von der Show gelöscht: {stand29[26]}"

    #
    # Die Farbe muss die Show trotzdem stellen - sonst waere aus dem
    # "nicht anfassen" ein "gar nichts mehr tun" geworden.
    #
    assert stand29[0] > 200, f"Die Show stellt die Farbe nicht mehr: {stand29[:3]}"

    print("OK: Die Show lässt von Hand gestellte Kanäle stehen")


# ====================================================================
# 10. Der belegte Adressbereich steht im Statusbericht
#
# Ausrechnen koennte die Oberflaeche ihn selbst - dann stuende die
# Regel aber an zwei Stellen, und eine davon wuerde irgendwann
# vergessen.
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    licht = ablage(Path(tmp))
    licht.set_enabled(True)

    licht.lampe_speichern({
        "id": "gross", "name": "KLS gross",
        "template": "eurolite-kls-180-6-29", "address": 30,
    })
    licht.lampe_speichern({
        "id": "klein", "name": "Dimmer",
        "template": "dimmer", "address": 100,
    })

    lampen = {l["id"]: l for l in licht.uebersicht()["fixtures"]}

    assert lampen["gross"]["last_address"] == 58, lampen["gross"]
    assert lampen["klein"]["last_address"] == 100, lampen["klein"]

    print("OK: Zu jeder Lampe steht der letzte belegte Kanal im Bericht")


# ====================================================================
# 11. Lampenarten: Effekt, Hintergrund, ausgenommen
#
# Der Grund fuer die Arten: Bisher zuckelte jede Lampe im Takt. Bei
# einem ganzen Rig fehlt damit das ruhige Grundlicht, vor dem sich
# ein Effekt ueberhaupt erst abheben kann.
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    #
    # Eine Lampe, die noch ohne Art in der Ablage liegt - so sieht
    # jede Einrichtung aus, die vor diesem Umbau angelegt wurde. Sie
    # muss sich nach dem Update genau wie vorher verhalten.
    #
    speicher = StateStore(Path(tmp) / "state.json")
    speicher.set("dmx_config", {
        "enabled": True,
        "templates": [],
        "fixtures": [{"id": "alt", "name": "Alt", "template": "rgb",
                      "address": 1}],
        "scenes": [],
        "show": {},
    })

    licht = LightingStore(speicher)

    assert licht.lampen()[0]["kind"] == "effect", licht.lampen()[0]

    print("OK: Eine Lampe ohne Art gilt als Effektlicht - wie vor dem Umbau")

    ok, meldung = licht.lampe_speichern({
        "id": "x", "name": "X", "template": "rgb", "address": 20,
        "kind": "irgendwas",
    })

    assert not ok and "Art" in meldung, meldung

    print("OK: Eine unbekannte Art wird abgewiesen")


with tempfile.TemporaryDirectory() as tmp:

    licht = ablage(Path(tmp))
    licht.set_enabled(True)

    licht.lampe_speichern({
        "id": "effekt", "name": "Effekt", "template": "bar-8-rgb",
        "address": 1, "kind": "effect",
    })
    licht.lampe_speichern({
        "id": "wash", "name": "Wash", "template": "bar-8-rgb",
        "address": 30, "kind": "background",
    })
    licht.lampe_speichern({
        "id": "fest", "name": "Ambient", "template": "rgb",
        "address": 100, "kind": "static",
    })

    app = LichtApp(licht, DmxAttrappe())
    motor = app.light_engine

    motor.einstellungen = {"sensitivity": 1.0, "background_seconds": 4.0}

    #
    # Erst Stille, damit die Glaettung von unten losfaehrt.
    #
    motor.stand = {"low": 0.0, "mid": 0.0, "high": 0.0,
                   "level": 0.0, "beat": False}
    motor.werte_je_lampe()

    #
    # Jetzt volle Musik. Die entscheidende Eigenschaft ist NICHT,
    # dass der Hintergrund ankommt - das taete er auch ohne jede
    # Glaettung, nur sofort. Entscheidend ist beides zusammen: nach
    # einem Block kaum bewegt, nach sechs Sekunden weitgehend da.
    #
    motor.stand = {"low": 1.0, "mid": 1.0, "high": 1.0,
                   "level": 0.9, "beat": False}

    nach_einem = max(motor.werte_je_lampe()["wash"])

    for _ in range(299):
        werte = motor.werte_je_lampe()

    nach_sechs = max(werte["wash"])
    sofort = max(werte["effekt"])

    assert nach_einem < 0.05 * sofort, (
        f"Der Hintergrund springt: nach einem Block schon {nach_einem} "
        f"von {sofort}."
    )
    assert nach_sechs > 0.70 * sofort, (
        f"Der Hintergrund kommt nicht an: nach 6 s erst {nach_sechs} "
        f"von {sofort}."
    )

    print(
        f"OK: Das Hintergrundlicht zieht langsam nach "
        f"({nach_einem} nach 20 ms, {nach_sechs} nach 6 s, Ziel {sofort})"
    )

    #
    # Und es hat kein Lauflicht. Geprueft wird gegen das Effektlicht
    # im selben Bild - sonst belegt der Test nur, dass irgendetwas
    # gleichfoermig ist.
    #
    for schritt in range(20):

        motor.position = schritt
        werte = motor.werte_je_lampe()

        wash = [werte["wash"][i] for i in range(0, 24, 3)]
        effekt = [werte["effekt"][i] for i in range(0, 24, 3)]

        assert len(set(wash)) == 1, (
            f"Das Hintergrundlicht hat ein Lauflicht: {wash}"
        )
        assert len(set(effekt)) > 1, (
            f"Dem Effektlicht fehlt das Lauflicht: {effekt}"
        )

    print("OK: Nur das Effektlicht hat ein Lauflicht, der Hintergrund nicht")


    #
    # Eine ausgenommene Lampe behaelt, was von Hand eingestellt wurde -
    # ueber viele Bilder hinweg.
    #
    ok, meldung = app.set_light_fixture_values("fest", [10, 20, 30])
    assert ok, meldung

    for _ in range(50):
        app.licht_show_bild(motor.werte_je_lampe())

    assert app.light_values["fest"] == [10, 20, 30], app.light_values["fest"]

    print("OK: Eine ausgenommene Lampe überlebt 50 Show-Bilder")

    #
    # Auch der Rueckfall auf die Stille-Szene laesst sie stehen. Das
    # ist der Punkt, an dem eine Ausnahme am ehesten durchgerutscht
    # waere: Der Rueckfall ersetzt sonst das ganze Bild.
    #
    app.light_values["effekt"] = [255] * 24
    ok, meldung = app.save_light_scene("Pause")
    assert ok, meldung

    szene = licht.szenen()[0]["id"]

    ok, meldung = app.set_light_show_settings({"fallback_scene": szene})
    assert ok, meldung

    app.set_light_fixture_values("fest", [7, 8, 9])

    app.licht_rueckfall("silence")

    assert app.light_values["fest"] == [7, 8, 9], (
        f"Der Rückfall hat die ausgenommene Lampe überschrieben: "
        f"{app.light_values['fest']}"
    )
    assert app.light_values["effekt"] == [255] * 24, (
        "Der Rückfall hat die Szene nicht aufgerufen."
    )

    print("OK: Auch der Rückfall auf eine Szene lässt sie in Ruhe")


with tempfile.TemporaryDirectory() as tmp:

    #
    # Drehung und Laser bleiben beim Hintergrundlicht aus. Ein
    # rotierender Derby als Grundlicht waere ein Widerspruch.
    #
    licht = ablage(Path(tmp))
    licht.set_enabled(True)

    licht.lampe_speichern({
        "id": "bar", "name": "Laser-Bar",
        "template": "eurolite-kls-laser-bar-pro-fx-28",
        "address": 1, "kind": "background",
    })

    app = LichtApp(licht, DmxAttrappe())
    motor = app.light_engine

    motor.einstellungen = {"sensitivity": 1.0}
    motor.stand = {"low": 1.0, "mid": 1.0, "high": 1.0,
                   "level": 0.9, "beat": False}

    werte = motor.werte_je_lampe()["bar"]

    assert werte[20] == 0 and werte[21] == 0, f"Laser an: {werte[20:22]}"
    assert werte[4] == 0 and werte[19] == 0, f"Drehung an: {werte[4]}"

    print("OK: Als Hintergrundlicht bleiben Drehung und Laser aus")


# ====================================================================
# 12. Das Hintergrundlicht wechselt zwischen den drei Farben
#
# Zuerst wurden alle drei Bandfarben ADDIERT. Bei halbwegs
# ausgewogener Musik stand damit dauerhaft ihre Summe da - und mit
# der ueblichen Vorgabe Rot plus Gruen plus Blau ist das schlicht
# Weiss. Es wechselte also gar nichts. Genau das prueft dieser
# Abschnitt.
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    licht = ablage(Path(tmp))
    licht.set_enabled(True)

    licht.lampe_speichern({
        "id": "wash", "name": "Wash", "template": "rgb",
        "address": 1, "kind": "background",
    })
    licht.lampe_speichern({
        "id": "effekt", "name": "Effekt", "template": "rgb",
        "address": 10, "kind": "effect",
    })

    app = LichtApp(licht, DmxAttrappe())
    motor = app.light_engine

    motor.einstellungen = {
        "sensitivity": 1.0,
        "background_seconds": 1.0,
        "background_beats": 8,
        "color_low": "#ff0000",
        "color_mid": "#00ff00",
        "color_high": "#0000ff",
    }

    #
    # Alle drei Baender voll - der Fall, in dem die alte Rechnung
    # Weiss ergab.
    #
    motor.stand = {"low": 1.0, "mid": 1.0, "high": 1.0,
                   "level": 0.9, "beat": False}

    for _ in range(300):
        werte = motor.werte_je_lampe()

    wash = werte["wash"]
    effekt = werte["effekt"]

    assert effekt == [255, 255, 255], (
        f"Das Effektlicht soll weiterhin mischen: {effekt}"
    )

    assert wash[0] > 200 and wash[1] < 40 and wash[2] < 40, (
        f"Das Hintergrundlicht zeigt keine reine Farbe, sondern {wash} - "
        f"genau der Mischmasch, der behoben werden sollte."
    )

    print("OK: Das Hintergrundlicht zeigt eine Farbe, das Effektlicht die Mischung")

    #
    # Weiss, Amber und UV bleiben aus - sie wuerden genau die Farbe
    # verwaschen, um die es hier geht.
    #
    licht.lampe_speichern({
        "id": "rgbw", "name": "RGBW", "template": "rgbw",
        "address": 30, "kind": "background",
    })

    for _ in range(50):
        werte = motor.werte_je_lampe()

    assert werte["rgbw"][3] == 0, (
        f"Weiß verwässert die Hintergrundfarbe: {werte['rgbw']}"
    )

    print("OK: Weiß bleibt beim Hintergrundlicht aus")

    #
    # Weitergeschaltet wird nach Schlaegen. Genau nach acht, nicht
    # nach sieben und nicht nach neun.
    #
    motor.hintergrund_farbe = 0
    motor.hintergrund_schlaege = 0
    motor.hintergrund_zeit = 0.0

    for _ in range(7):
        motor._farbe_weiterschalten(0.02, True)

    assert motor.hintergrund_farbe == 0, (
        f"Zu früh weitergeschaltet, nach 7 Schlägen: "
        f"{motor.hintergrund_farbe}"
    )

    motor._farbe_weiterschalten(0.02, True)

    assert motor.hintergrund_farbe == 1, (
        f"Nach 8 Schlägen nicht weitergeschaltet: {motor.hintergrund_farbe}"
    )

    print("OK: Der Farbwechsel kommt nach genau der eingestellten Zahl Schläge")

    #
    # Und ohne jeden Schlag geht es nach der Uhr weiter. Ohne diesen
    # Notnagel stuende die Farbe bei einer ruhigen Passage still, und
    # das saehe aus wie ein Fehler.
    #
    motor.hintergrund_farbe = 0
    motor.hintergrund_schlaege = 0
    motor.hintergrund_zeit = 0.0

    # 8 Schläge x 1,5 s = 12 s. Nach 10 s darf noch nichts passiert
    # sein, nach 13 s muss es.
    for _ in range(500):
        motor._farbe_weiterschalten(0.02, False)

    assert motor.hintergrund_farbe == 0, (
        "Der Zeitweg greift zu früh - er soll nur einspringen, wenn "
        "die Takterkennung wirklich nichts findet."
    )

    for _ in range(150):
        motor._farbe_weiterschalten(0.02, False)

    assert motor.hintergrund_farbe == 1, (
        "Ohne Takt bleibt die Farbe stehen, statt nach der Uhr "
        "weiterzugehen."
    )

    print("OK: Ohne erkannten Takt geht der Wechsel nach der Uhr weiter")

    #
    # Über einen ganzen Durchlauf müssen alle drei Farben vorkommen -
    # sonst wäre es kein Wechsel, sondern eine Vorliebe.
    #
    motor.hintergrund_farbe = 0
    motor._hintergrund.clear()

    gesehen = set()

    for schritt in range(2400):

        motor._farbe_weiterschalten(0.02, schritt % 25 == 0)
        wash = motor.werte_je_lampe()["wash"]

        if wash[0] > 200 and wash[1] < 40: gesehen.add("rot")
        if wash[1] > 200 and wash[0] < 40: gesehen.add("gruen")
        if wash[2] > 200 and wash[0] < 40: gesehen.add("blau")

    assert gesehen == {"rot", "gruen", "blau"}, (
        f"Nicht alle drei Farben kamen vor: {gesehen}"
    )

    print("OK: Über einen Durchlauf kommen alle drei Farben satt vor")


# ====================================================================
# 13. Die zweite Hintergrundgruppe
#
# Zwei Gruppen mit eigenen Farben und gegeneinander versetzt: Damit
# stehen immer zwei verschiedene Farben auf der Buehne statt einer.
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    licht = ablage(Path(tmp))
    licht.set_enabled(True)

    licht.lampe_speichern({
        "id": "a", "name": "Wash A", "template": "rgb",
        "address": 1, "kind": "background",
    })
    licht.lampe_speichern({
        "id": "b", "name": "Wash B", "template": "rgb",
        "address": 10, "kind": "background2",
    })
    licht.lampe_speichern({
        "id": "e", "name": "Effekt", "template": "rgb",
        "address": 20, "kind": "effect",
    })

    app = LichtApp(licht, DmxAttrappe())
    motor = app.light_engine

    #
    # Zwei klar unterscheidbare Paletten: Satz 1 rein rot/gruen/blau,
    # Satz 2 rein weiss - so ist an einem Kanalwert sofort zu sehen,
    # aus welchem Satz eine Farbe stammt.
    #
    motor.einstellungen = {
        "sensitivity": 1.0,
        "background_seconds": 1.0,
        "background_beats": 8,
        "color_low": "#ff0000",
        "color_mid": "#00ff00",
        "color_high": "#0000ff",
        "color_low_2": "#ffffff",
        "color_mid_2": "#ffffff",
        "color_high_2": "#ffffff",
    }

    motor.stand = {"low": 1.0, "mid": 1.0, "high": 1.0,
                   "level": 0.9, "beat": False}

    for _ in range(300):
        werte = motor.werte_je_lampe()

    assert werte["b"][0] > 200 and werte["b"][1] > 200 and werte["b"][2] > 200, (
        f"Gruppe 2 benutzt nicht ihren eigenen Farbsatz: {werte['b']}"
    )
    assert werte["a"][1] < 40 or werte["a"][2] < 40, (
        f"Gruppe 1 hat den Farbsatz der zweiten erwischt: {werte['a']}"
    )
    assert werte["e"] == [255, 255, 255], (
        f"Das Effektlicht mischt nicht mehr den ersten Satz: {werte['e']}"
    )

    print("OK: Jede Hintergrundgruppe benutzt ihren eigenen Farbsatz")

    #
    # Der Versatz: Mit der GLEICHEN Palette in beiden Saetzen muessen
    # die Gruppen trotzdem verschiedene Farben zeigen. Ohne diese
    # Prüfung koennte der Versatz fehlen, ohne dass es auffiele -
    # solange die Paletten verschieden sind, sieht es ja ohnehin
    # anders aus.
    #
    motor.einstellungen.update({
        "color_low_2": "#ff0000",
        "color_mid_2": "#00ff00",
        "color_high_2": "#0000ff",
    })
    motor._hintergrund.clear()
    motor.hintergrund_farbe = 0
    motor.hintergrund_schlaege = 0
    motor.hintergrund_zeit = 0.0

    gleich = 0
    proben = 0

    for schritt in range(2400):

        motor._farbe_weiterschalten(0.02, schritt % 25 == 0)
        werte = motor.werte_je_lampe()

        #
        # Nur messen, wenn eine Farbe wirklich steht - waehrend der
        # Blende sind beide unterwegs, und ein Vergleich mittendrin
        # sagt nichts.
        #
        if max(werte["a"]) > 240:
            proben += 1
            if werte["a"] == werte["b"]:
                gleich += 1

    assert proben > 100, f"Zu wenige brauchbare Proben: {proben}"
    assert gleich == 0, (
        f"Bei gleicher Palette zeigen beide Gruppen dieselbe Farbe "
        f"({gleich} von {proben} Proben) - der Versatz fehlt."
    )

    print(f"OK: Die Gruppen laufen versetzt ({proben} Proben, keine gleich)")


# ====================================================================
# 14. Kein Weiß mehr auf den Effektlampen
#
# Am Geraet gemeldet: "Bei den KLS-180/6 und den Lampen an der Laser
# Bar sieht das Licht groesstenteils weiss aus." Zwei Ursachen, beide
# hier geprueft:
#
#   1. Jedes Segment bekam die MISCHUNG aller drei Baender. Rot plus
#      Gruen plus Blau ist Weiss.
#   2. Auf einem RGBW-Spot lief der Weiss-Kanal mit dem mittleren Band
#      mit und wusch die Farbe zusaetzlich aus.
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    licht = ablage(Path(tmp))
    licht.set_enabled(True)

    licht.lampe_speichern({
        "id": "kls", "name": "KLS", "template": "eurolite-kls-180-6-24",
        "address": 1, "kind": "effect",
    })
    licht.lampe_speichern({
        "id": "bar", "name": "Laser-Bar",
        "template": "eurolite-kls-laser-bar-pro-fx-28",
        "address": 40, "kind": "effect",
    })

    app = LichtApp(licht, DmxAttrappe())
    motor = app.light_engine

    motor.einstellungen = {
        "sensitivity": 1.0,
        "color_low": "#ff0000",
        "color_mid": "#00ff00",
        "color_high": "#0000ff",
    }

    #
    # Der gemeldete Fall: Musik mit allem drin.
    #
    motor.stand = {"low": 1.0, "mid": 1.0, "high": 1.0,
                   "level": 0.9, "beat": False}

    for schritt in range(12):

        motor.position = schritt
        werte = motor.werte_je_lampe()

        #
        # Die sechs Spots der KLS: jeder darf nur EINEN Farbkanal
        # anhaben. Sind zwei oder drei an, ist es wieder eine
        # Mischung - und drei sind Weiss.
        #
        for spot in range(6):

            rot, gruen, blau, weiss = werte["kls"][spot * 4:spot * 4 + 4]

            an = [wert for wert in (rot, gruen, blau) if wert > 0]

            assert len(an) == 1, (
                f"Spot {spot + 1} bekommt eine Mischung statt einer Farbe: "
                f"R{rot} G{gruen} B{blau}"
            )

            assert weiss == 0, (
                f"Spot {spot + 1} bekommt Weiß dazu, das wäscht die Farbe "
                f"aus: {weiss}"
            )

        #
        # Und die vier Farbeinheiten der Laser Bar genauso.
        #
        for start in (0, 5, 10, 15):

            rot, gruen, blau = werte["bar"][start:start + 3]

            an = [wert for wert in (rot, gruen, blau) if wert > 0]

            assert len(an) == 1, (
                f"Laser-Bar ab Kanal {start + 1} bekommt eine Mischung: "
                f"R{rot} G{gruen} B{blau}"
            )

    print("OK: Jede Einheit zeigt genau eine Farbe, kein Weiß")

    #
    # Über die sechs Spots hinweg muessen ALLE drei Baender vorkommen -
    # sonst waere aus dem Weiss nur eine einzige Farbe geworden.
    #
    motor.position = 0
    werte = motor.werte_je_lampe()["kls"]

    baender = set()

    for spot in range(6):
        rot, gruen, blau, _ = werte[spot * 4:spot * 4 + 4]
        if rot: baender.add("rot")
        if gruen: baender.add("gruen")
        if blau: baender.add("blau")

    assert baender == {"rot", "gruen", "blau"}, (
        f"Nicht alle drei Bänder kommen auf der Lampe vor: {baender}"
    )

    print("OK: Über die sechs Spots verteilen sich alle drei Bänder")

    #
    # Ein von Hand gesetzter Weissanteil bleibt jetzt stehen - die
    # Show fasst diese Kanaele nicht mehr an. Damit ist der
    # Weiss-Kanal nicht verloren, sondern nur nicht mehr
    # aufgezwungen.
    #
    vonHand = [0] * 24
    vonHand[3] = 120        # Weiss von Spot 1

    ok, meldung = app.set_light_fixture_values("kls", vonHand)
    assert ok, meldung

    for _ in range(20):
        app.licht_show_bild(motor.werte_je_lampe())

    assert app.light_values["kls"][3] == 120, (
        f"Ein von Hand gesetzter Weißanteil überlebt die Show nicht: "
        f"{app.light_values['kls'][3]}"
    )

    print("OK: Weiß von Hand eingestellt bleibt während der Show stehen")


with tempfile.TemporaryDirectory() as tmp:

    #
    # Eine Lampe ohne Segmente kann die Baender nicht nebeneinander
    # zeigen - fuer sie bleibt es bei der Mischung. Bekaeme sie ein
    # einzelnes Band, reagierte ein einzelner RGB-Strahler nur noch
    # auf den Bass und ignorierte die halbe Musik.
    #
    licht = ablage(Path(tmp))
    licht.set_enabled(True)

    licht.lampe_speichern({
        "id": "par", "name": "Par", "template": "rgb",
        "address": 1, "kind": "effect",
    })

    app = LichtApp(licht, DmxAttrappe())
    motor = app.light_engine

    motor.einstellungen = {
        "sensitivity": 1.0,
        "color_low": "#ff0000",
        "color_mid": "#00ff00",
        "color_high": "#0000ff",
    }
    motor.stand = {"low": 1.0, "mid": 1.0, "high": 1.0,
                   "level": 0.9, "beat": False}

    werte = motor.werte_je_lampe()["par"]

    assert werte == [255, 255, 255], (
        f"Eine einzelne Lampe soll weiter mischen: {werte}"
    )

    print("OK: Eine Lampe ohne Segmente mischt weiterhin alle drei Bänder")


# ====================================================================
# 15. Die Blende in die Rückfallszene
#
# Am Songende hart auf die Szene umzuschalten ist ein sichtbarer
# Sprung, und zwar genau in dem Moment, in dem es ruhig werden soll.
#
# Der Rueckweg bleibt mit Absicht hart: Die Show setzt mit dem ersten
# Takt des naechsten Songs sofort ein.
# ====================================================================

def blenden_aufbau(ordner: Path, dauer: float = 2.0):
    """Eine Lampe, eine Szene, und die Show auf Rot."""

    licht = ablage(ordner)
    licht.set_enabled(True)
    licht.lampe_speichern({
        "id": "p", "name": "Par", "template": "rgb", "address": 1,
    })

    dmx = DmxAttrappe()
    app = LichtApp(licht, dmx)

    # Die Szene: tiefblau.
    app.light_values = {"p": [0, 0, 120]}
    app.save_light_scene("Pause")

    szene = licht.szenen()[0]["id"]

    ok, meldung = licht.set_show_einstellungen({
        "fallback_scene": szene, "fade_seconds": dauer,
    })
    assert ok, meldung

    # Und die laufende Show: hellrot.
    app.light_values = {"p": [255, 0, 0]}
    app._licht_senden()

    return licht, app, dmx


with tempfile.TemporaryDirectory() as tmp:

    licht, app, dmx = blenden_aufbau(Path(tmp), dauer=2.0)

    app.licht_rueckfall("silence")

    #
    # Drei Punkte statt einem.
    #
    # Nur zu pruefen, dass die Szene am Ende steht, waere auch ohne
    # jede Blende erfuellt - dann eben sofort. Erst der Anfang und die
    # Mitte zusammen belegen, dass wirklich geblendet wird.
    #
    assert app.light_values["p"] == [255, 0, 0], (
        f"Im Moment des Übergangs darf sich noch nichts bewegt haben: "
        f"{app.light_values['p']}"
    )

    for _ in range(50):                       # 50 x 20 ms = 1 s
        app.licht_rueckfall_halten(0.02)

    mitte = app.light_values["p"]

    assert 100 < mitte[0] < 155 and 40 < mitte[2] < 80, (
        f"Nach der halben Zeit muss es etwa in der Mitte stehen: {mitte}"
    )

    for _ in range(50):
        app.licht_rueckfall_halten(0.02)

    assert app.light_values["p"] == [0, 0, 120], (
        f"Nach der vollen Zeit muss die Szene stehen: {app.light_values['p']}"
    )

    #
    # Und danach passiert nichts mehr - der Tick laeuft weiter, solange
    # keine Musik kommt.
    #
    vorher = len(dmx.gesendet)

    for _ in range(20):
        app.licht_rueckfall_halten(0.02)

    assert len(dmx.gesendet) == vorher, (
        "Eine durchgelaufene Blende sendet weiter, obwohl sich nichts "
        "mehr ändert."
    )

    print("OK: Es wird über die eingestellte Zeit in die Szene geblendet")


with tempfile.TemporaryDirectory() as tmp:

    #
    # Kommt die Musik mitten in der Blende zurueck, gilt das Show-Bild
    # SOFORT und vollstaendig. Ohne das Abbrechen zoege der naechste
    # Tick das Licht wieder Richtung Szene.
    #
    licht, app, dmx = blenden_aufbau(Path(tmp), dauer=2.0)

    app.licht_rueckfall("silence")

    for _ in range(50):
        app.licht_rueckfall_halten(0.02)

    app.licht_show_bild({"p": [0, 255, 0]})

    assert app.light_values["p"] == [0, 255, 0], (
        f"Das Show-Bild muss sofort und ganz gelten: {app.light_values['p']}"
    )

    app.licht_rueckfall_halten(0.02)

    assert app.light_values["p"] == [0, 255, 0], (
        f"Die Blende lief weiter, obwohl die Musik zurück ist: "
        f"{app.light_values['p']}"
    )

    print("OK: Kommt die Musik zurück, setzt die Show sofort und ganz ein")


with tempfile.TemporaryDirectory() as tmp:

    #
    # Auf 0 gestellt: hartes Umschalten wie vorher. Das ist zugleich
    # die Ruecksicherung darauf, dass das alte Verhalten erreichbar
    # bleibt.
    #
    licht, app, dmx = blenden_aufbau(Path(tmp), dauer=0.0)

    app.licht_rueckfall("silence")

    assert app.light_values["p"] == [0, 0, 120], (
        f"Mit 0 Sekunden muss sofort umgeschaltet werden: "
        f"{app.light_values['p']}"
    )

    print("OK: Auf 0 gestellt schaltet es hart um wie vorher")


with tempfile.TemporaryDirectory() as tmp:

    #
    # Blackout ist der Knopf fuer den Fall, dass etwas schiefgeht. Er
    # darf nie durch die Blende laufen - zwei Sekunden, bis es dunkel
    # wird, sind hier zwei Sekunden zu viel.
    #
    licht, app, dmx = blenden_aufbau(Path(tmp), dauer=2.0)

    app.licht_rueckfall("silence")

    for _ in range(25):
        app.licht_rueckfall_halten(0.02)

    app.light_blackout()

    assert set(dmx.gesendet[-1]) == {0}, (
        f"Blackout mitten in der Blende ist nicht sofort dunkel: "
        f"{dmx.gesendet[-1][:6]}"
    )

    app.licht_rueckfall_halten(0.02)

    assert set(dmx.gesendet[-1]) == {0}, (
        "Nach dem Blackout zieht die Blende das Licht wieder hoch."
    )

    print("OK: Blackout wirkt sofort, auch mitten in der Blende")


with tempfile.TemporaryDirectory() as tmp:

    #
    # Die Helligkeit ist die Stelle, an der man sich am leichtesten
    # vertut.
    #
    # Eine Lampe ohne Eintrag in light_brightness gilt als VOLL
    # aufgedreht - so liest es fixtures.bild(). Wer beim Mischen einen
    # fehlenden Eintrag als 0 nimmt, dimmt sie waehrend der Blende auf
    # null herunter und wieder hoch. Am Geraet saehe das aus wie ein
    # Wackelkontakt.
    #
    licht = ablage(Path(tmp))
    licht.set_enabled(True)
    licht.lampe_speichern({
        "id": "p", "name": "Par", "template": "rgb", "address": 1,
    })

    dmx = DmxAttrappe()
    app = LichtApp(licht, dmx)

    #
    # Der riskante Fall ist, dass EINE Seite einen Eintrag hat und die
    # andere nicht - haetten beide keinen, wuerde gar nicht erst
    # gemischt, und der Test belegte nichts.
    #
    # Hier: Die Szene wird ohne Helligkeit gespeichert, die laufende
    # Show hat volle Helligkeit eingetragen. Beide bedeuten dasselbe,
    # naemlich voll aufgedreht - also darf sich waehrend der Blende
    # nichts bewegen.
    #
    app.light_values = {"p": [0, 0, 255]}
    app.light_brightness = {}
    app.save_light_scene("Pause")

    szene = licht.szenen()[0]["id"]
    licht.set_show_einstellungen({"fallback_scene": szene, "fade_seconds": 2.0})

    app.light_values = {"p": [255, 0, 0]}
    app.light_brightness = {"p": 255}

    app.licht_rueckfall("silence")

    for schritt in range(100):

        app.licht_rueckfall_halten(0.02)

        assert app.light_brightness.get("p", 255) == 255, (
            f"Die Helligkeit wurde heruntergezogen, obwohl beide Seiten "
            f"voll sind - Schritt {schritt}: {app.light_brightness}"
        )

    print("OK: Eine fehlende Helligkeit gilt als voll, nicht als null")


with tempfile.TemporaryDirectory() as tmp:

    #
    # Ausgenommene Lampen stehen ueber die ganze Blende hinweg still.
    #
    licht = ablage(Path(tmp))
    licht.set_enabled(True)
    licht.lampe_speichern({
        "id": "p", "name": "Par", "template": "rgb", "address": 1,
    })
    licht.lampe_speichern({
        "id": "fest", "name": "Ambient", "template": "rgb",
        "address": 10, "kind": "static",
    })

    dmx = DmxAttrappe()
    app = LichtApp(licht, dmx)

    app.light_values = {"p": [0, 0, 120], "fest": [10, 20, 30]}
    app.save_light_scene("Pause")

    szene = licht.szenen()[0]["id"]
    licht.set_show_einstellungen({"fallback_scene": szene, "fade_seconds": 2.0})

    app.light_values = {"p": [255, 0, 0], "fest": [77, 88, 99]}

    app.licht_rueckfall("silence")

    for schritt in range(120):

        app.licht_rueckfall_halten(0.02)

        assert app.light_values["fest"] == [77, 88, 99], (
            f"Die ausgenommene Lampe bewegt sich mit - Schritt {schritt}: "
            f"{app.light_values['fest']}"
        )

    assert app.light_values["p"] == [0, 0, 120], app.light_values["p"]

    print("OK: Ausgenommene Lampen stehen auch während der Blende still")


# ====================================================================
# 16. Die Show erbt die Helligkeit der Rückfallszene nicht
#
# Am Geraet gemeldet: Wer die statische Szene mit heruntergezogenen
# Reglern angelegt hatte, bekam anschliessend eine Show, die dauerhaft
# gedimmt lief.
#
# Ursache: licht_show_bild() setzte nur light_values. light_brightness
# blieb stehen, wie der Rueckfall es aus der Szene uebernommen hatte -
# und _licht_senden() legt es beim Senden wieder drauf. Die Farbwerte
# stimmten, die Helligkeit darunter nicht.
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    licht = ablage(Path(tmp))
    licht.set_enabled(True)
    licht.lampe_speichern({
        "id": "p", "name": "Par", "template": "rgb", "address": 1,
    })
    licht.lampe_speichern({
        "id": "fest", "name": "Ambient", "template": "rgb",
        "address": 10, "kind": "static",
    })

    dmx = DmxAttrappe()
    app = LichtApp(licht, dmx)

    #
    # Eine Szene mit deutlich heruntergezogener Helligkeit - genau
    # der gemeldete Fall.
    #
    app.set_light_fixture_values("p", [255, 255, 255])
    app.set_light_fixture_brightness("p", 51)
    app.set_light_fixture_values("fest", [255, 0, 0])
    app.set_light_fixture_brightness("fest", 80)

    ok, meldung = app.save_light_scene("Pause")
    assert ok, meldung

    szene = licht.szenen()[0]["id"]

    ok, meldung = licht.set_show_einstellungen({
        "fallback_scene": szene, "fade_seconds": 0.0,
    })
    assert ok, meldung

    #
    # Songende: Rueckfall auf die gedimmte Szene.
    #
    app.licht_rueckfall("silence")
    blende_zuende(app)

    assert dmx.gesendet[-1][0:3] == [51, 51, 51], (
        f"Die Szene muss gedimmt zurückkommen: {dmx.gesendet[-1][0:3]}"
    )

    #
    # Und jetzt kommt die Musik zurück. Geprüft wird am gesendeten
    # Rahmen, nicht an light_brightness: Auf dem Kabel steht, was die
    # Lampen wirklich bekommen.
    #
    #
    # So, wie der Show-Thread es tut: Ausgenommene Lampen sind im Bild
    # mit drin, mit ihren bisherigen Werten (siehe
    # LightEngine.werte_je_lampe). Sie wegzulassen waere hier ein
    # Fehler im Test, nicht im Programm.
    #
    app.licht_show_bild({"p": [255, 255, 255], "fest": [255, 0, 0]})

    assert dmx.gesendet[-1][0:3] == [255, 255, 255], (
        f"Die Show läuft auf der Helligkeit der Szene weiter: "
        f"{dmx.gesendet[-1][0:3]}"
    )

    #
    # Die ausgenommene Lampe behält ihre - sie gehört nicht der Show.
    #
    assert dmx.gesendet[-1][9] == 80, (
        f"Die Helligkeit der ausgenommenen Lampe wurde mit "
        f"zurückgesetzt: {dmx.gesendet[-1][9]}"
    )

    print("OK: Die Show dreht auf, statt die Helligkeit der Szene zu erben")

    #
    # Die Gegenseite, und der eigentlich wichtige Teil: Ein von Hand
    # eingestellter Wert muss die Show ueberleben.
    #
    # Wuerde jedes Show-Bild die Helligkeit zuruecksetzen, waere der
    # Regler in der Karte waehrend der Show wirkungslos und spraenge
    # nach jedem Ziehen auf voll zurueck - genau der Fehler aus 1.13.
    #
    ok, meldung = app.set_light_fixture_brightness("p", 128)
    assert ok, meldung

    for _ in range(20):
        app.licht_show_bild({"p": [255, 255, 255], "fest": [255, 0, 0]})

    assert dmx.gesendet[-1][0:3] == [128, 128, 128], (
        f"Ein von Hand eingestellter Wert überlebt die Show nicht: "
        f"{dmx.gesendet[-1][0:3]}"
    )

    print("OK: Von Hand eingestellte Helligkeit bleibt während der Show stehen")


# ====================================================================
# 17. Szenennamen sind eindeutig
#
# Szenen werden ueberall ueber ihren Namen ausgewaehlt - in der Karte
# und in der Rueckfall-Auswahl. Zwei Szenen "Pause" sind dort nicht
# auseinanderzuhalten: Man klickt eine und bekommt vielleicht die
# andere.
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    licht = ablage(Path(tmp))
    licht.set_enabled(True)

    ok, meldung, kennung = licht.szene_speichern("Pause", {})
    assert ok, meldung

    for zweiter in ("Pause", "pause", "  PAUSE  "):

        ok, meldung, _ = licht.szene_speichern(zweiter, {})

        assert not ok and "gibt es schon" in meldung, (
            f"'{zweiter}' wurde angenommen: {meldung}"
        )

    print("OK: Ein zweites Mal derselbe Szenenname wird abgewiesen")

    #
    # Die Gegenseite, und die Stelle, an der eine zu strenge Pruefung
    # Schaden anrichtet: Eine VORHANDENE Szene muss sich weiter unter
    # ihrem eigenen Namen speichern lassen. Diese Funktion legt nicht
    # nur an, sie aendert auch.
    #
    ok, meldung, zurueck = licht.szene_speichern("Pause", {}, kennung)

    assert ok, f"Die eigene Szene lässt sich nicht mehr speichern: {meldung}"
    assert zurueck == kennung, (zurueck, kennung)
    assert len(licht.szenen()) == 1, licht.szenen()

    print("OK: Eine vorhandene Szene lässt sich unter ihrem Namen speichern")


# ====================================================================
# 18. Drei getrennte Farbsätze
#
# Effektlicht, Hintergrundlicht 1 und Hintergrundlicht 2 haben jeder
# einen eigenen. Anfangs teilten sich Effektlicht und Hintergrund 1
# einen - das stand nirgends und fiel erst auf, als die Ueberschrift
# im Dialog stillschweigend fuer zwei Dinge galt.
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    #
    # Die Vorgaben von Satz 1 und dem namenlosen muessen gleich sein:
    # Eine vorhandene Einrichtung soll sich nach dem Update genauso
    # verhalten wie vorher.
    #
    vorgabe = ablage(Path(tmp)).show_einstellungen()

    for band in ("low", "mid", "high"):
        assert vorgabe[f"color_{band}"] == vorgabe[f"color_{band}_1"], (
            f"Satz 1 startet anders als der namenlose bei {band}: "
            f"{vorgabe[f'color_{band}']} vs {vorgabe[f'color_{band}_1']}"
        )

    print("OK: Hintergrund 1 startet mit denselben Farben wie vorher")


with tempfile.TemporaryDirectory() as tmp:

    licht = ablage(Path(tmp))
    licht.set_enabled(True)

    for kennung, art, adresse in (
        ("e", "effect", 1), ("h1", "background", 10), ("h2", "background2", 20),
    ):
        licht.lampe_speichern({
            "id": kennung, "name": kennung, "template": "rgb",
            "address": adresse, "kind": art,
        })

    app = LichtApp(licht, DmxAttrappe())
    motor = app.light_engine

    #
    # Drei Saetze, die sich an einem einzigen Kanal unterscheiden
    # lassen: rein rot, rein gruen, rein blau.
    #
    motor.einstellungen = {
        "sensitivity": 1.0,
        "background_seconds": 1.0,
        "background_beats": 8,
        "color_low": "#ff0000", "color_mid": "#ff0000", "color_high": "#ff0000",
        "color_low_1": "#00ff00", "color_mid_1": "#00ff00",
        "color_high_1": "#00ff00",
        "color_low_2": "#0000ff", "color_mid_2": "#0000ff",
        "color_high_2": "#0000ff",
    }

    motor.stand = {"low": 1.0, "mid": 1.0, "high": 1.0,
                   "level": 0.9, "beat": False}

    for _ in range(300):
        werte = motor.werte_je_lampe()

    assert werte["e"][0] > 200 and werte["e"][1] == 0, (
        f"Das Effektlicht nimmt nicht den namenlosen Satz: {werte['e']}"
    )
    assert werte["h1"][1] > 200 and werte["h1"][0] == 0, (
        f"Hintergrund 1 nimmt nicht seinen eigenen Satz: {werte['h1']}"
    )
    assert werte["h2"][2] > 200 and werte["h2"][0] == 0, (
        f"Hintergrund 2 nimmt nicht seinen Satz: {werte['h2']}"
    )

    print("OK: Jede der drei Arten benutzt ihren eigenen Farbsatz")

    #
    # Und eine unsinnige Farbe im neuen Satz wird genauso abgewiesen
    # wie in den anderen.
    #
    ok, meldung = licht.set_show_einstellungen({"color_mid_1": "grün"})
    assert not ok and "Farbe" in meldung, meldung

    ok, meldung = licht.set_show_einstellungen({"color_mid_1": "#123456"})
    assert ok, meldung

    print("OK: Auch der neue Satz wird auf gültige Farben geprüft")


# ====================================================================
# 19. Die Kanalzahl des Interfaces steht im Statusbericht
#
# Ohne sie kann die Oberflaeche die Auswahl der Kanalpaare nicht
# bauen, und man muesste die Zahl wieder eintippen.
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    app, _ = aufbau(Path(tmp))

    assert app.get_lighting_status()["input_channels"] == 8, (
        app.get_lighting_status().get("input_channels")
    )

    print("OK: Die Kanalzahl des Interfaces steht im Bericht")


# ====================================================================
# 20. Der zweite Show-Modus: Puls statt wandernder Punkt
#
# Bisher hatte die Show genau ein Bild fuer Effektlicht - ein heller
# Punkt, der im Takt ueber die Segmente wandert. Im Puls-Modus atmen
# stattdessen alle Segmente gemeinsam: Bei jedem Schlag gehen sie auf
# voll und fallen bis zum naechsten zurueck.
# ====================================================================

# --- Die Huellkurve -------------------------------------------------

with tempfile.TemporaryDirectory() as tmp:

    licht = ablage(Path(tmp))
    licht.set_enabled(True)

    motor = LichtApp(licht, DmxAttrappe()).light_engine

    motor.puls = 0.0
    motor._puls_weiterschalten(0.02, True)

    assert motor.puls == 1.0, (
        f"Ein Schlag muss den Puls sofort auf voll setzen: {motor.puls}"
    )

    #
    # Hart hoch, weich runter - wie bei den Huellkurven in
    # analysis.py. Ein Puls, der erst anschwillt, kaeme hinter dem
    # Schlag her, und das Licht saehe aus, als hinke es der Musik
    # hinterher.
    #
    vorher = motor.puls

    motor._puls_weiterschalten(0.02, False)

    assert motor.puls < vorher, "Ohne Schlag muss der Puls abfallen."

    #
    # Nach drei Zeitkonstanten ist praktisch nichts mehr da.
    #
    for _ in range(int(3 * motor.PULS_ABFALL_S / 0.02)):
        motor._puls_weiterschalten(0.02, False)

    assert 0.0 <= motor.puls < 0.1, (
        f"Nach drei Zeitkonstanten muss der Puls unten sein: {motor.puls}"
    )

    #
    # Und er darf nie unter Null rutschen - negative Helligkeit gaebe
    # es zwar nicht auf dem Kabel (begrenzen() faengt das), aber der
    # Fehler saesse dann hier und waere von aussen nicht zu sehen.
    #
    for _ in range(500):
        motor._puls_weiterschalten(0.02, False)

    assert motor.puls >= 0.0, motor.puls

    print("OK: Der Puls springt auf den Schlag und fällt weich zurück")


# --- Der Motor fuehrt den Puls auch wirklich ------------------------
#
# Die Huellkurve oben ist fuer sich geprueft. Sie nuetzt aber nichts,
# wenn sie im Betrieb niemand weiterdreht: Der Puls stuende dann
# stumm auf 0, und im Puls-Modus leuchteten alle Lampen dauerhaft mit
# Grundhelligkeit vor sich hin.

with tempfile.TemporaryDirectory() as tmp:

    from lighting.analysis import Stimmungserkennung

    class AnalyseAttrappe:
        """
        Liefert einen festen Analysestand.

        Der echten Bandanalyse einen Schlag unterzuschieben hiesse,
        ein Signal zu bauen, das sie als Schlag erkennt - das ist in
        test_light_analysis.py geprueft. Hier geht es allein darum,
        ob _schritt() den Puls weiterdreht.
        """

        rate = 48000
        channels = 2

        def __init__(self, schlag: bool):
            self.schlag = schlag

        def verarbeite(self, block):
            return {"low": 1.0, "mid": 0.2, "high": 0.1,
                    "level": 0.5, "beat": self.schlag}

    licht = ablage(Path(tmp))
    licht.set_enabled(True)
    licht.lampe_speichern({
        "id": "par", "name": "Par", "template": "rgb", "address": 1,
    })

    motor = LichtApp(licht, DmxAttrappe()).light_engine

    motor.erkennung = Stimmungserkennung(
        stille_schwelle=0.002, stille_sekunden=6.0, sprache_sekunden=0.0
    )

    motor.einstellungen = {"sensitivity": 1.0, "effect_mode": "pulse"}

    # 20 ms bei 48 kHz, zwei Kanaelen, 32 Bit.
    block = bytes(int(0.02 * 2 * 4 * 48000))

    motor.puls = 0.0
    motor.analyse = AnalyseAttrappe(True)
    motor._schritt(block)

    assert motor.puls == 1.0, (
        f"Ein Schlag im Betrieb muss den Puls setzen: {motor.puls}"
    )

    motor.analyse = AnalyseAttrappe(False)

    for _ in range(10):
        motor._schritt(block)

    assert motor.puls < 0.5, (
        f"Ohne Schlag muss der Puls im Betrieb abfallen: {motor.puls}"
    )

    print("OK: Der Show-Thread führt den Puls bei jedem Block weiter")


# --- Kein wandernder Punkt mehr -------------------------------------

with tempfile.TemporaryDirectory() as tmp:

    licht = ablage(Path(tmp))
    licht.set_enabled(True)
    licht.lampe_speichern({
        "id": "bar", "name": "LED-Bar", "template": "bar-8-rgb", "address": 1,
    })

    app = LichtApp(licht, DmxAttrappe())
    motor = app.light_engine

    #
    # Alle drei Baender gleich laut: Dann haengt der Unterschied
    # zwischen den Segmenten nur noch am Modus, nicht am Signal.
    #
    motor.stand = {"low": 1.0, "mid": 1.0, "high": 1.0, "level": 1.0, "beat": False}

    lauflicht = {
        "sensitivity": 1.0,
        "color_low": "#ff0000",
        "color_mid": "#00ff00",
        "color_high": "#0000ff",
    }

    motor.einstellungen = dict(lauflicht)
    motor.position = 0

    werte = motor.werte_je_lampe()["bar"]

    assert werte[0] > werte[4], (
        "Im Lauflicht muss das Segment, das dran ist, herausstechen: "
        f"{werte[:9]}"
    )

    #
    # Derselbe Augenblick im Puls-Modus, Puls auf voll: Jetzt sind
    # alle Segmente gleich hell - jedes in seiner Bandfarbe.
    #
    motor.einstellungen = {**lauflicht, "effect_mode": "pulse"}
    motor.puls = 1.0

    voll = motor.werte_je_lampe()["bar"]

    assert voll[0] == voll[4] == voll[8] == 255, (
        f"Im Puls müssen alle Segmente gleich hell sein: {voll[:9]}"
    )

    #
    # Und die Farbe je Segment bleibt: Segment 1 rot, 2 gruen, 3 blau.
    # Der Puls aendert die Helligkeit, nicht die Aufteilung der
    # Baender.
    #
    assert voll[0:3] == [255, 0, 0], voll[0:3]
    assert voll[3:6] == [0, 255, 0], voll[3:6]
    assert voll[6:9] == [0, 0, 255], voll[6:9]

    #
    # Die Position darf im Puls-Modus nichts mehr ausmachen. Sie
    # laeuft im Betrieb weiter mit, damit beim Umschalten nichts
    # springt - sichtbar sein darf sie aber nicht.
    #
    motor.position = 3

    assert motor.werte_je_lampe()["bar"] == voll, (
        "Im Puls-Modus darf die Position des Lauflichts nichts ändern."
    )

    print("OK: Im Puls-Modus leuchten alle Segmente gleich, ohne Punkt")

    #
    # Zwischen zwei Schlaegen faellt die Lampe auf den Boden zurueck -
    # denselben, mit dem beim Lauflicht die Segmente leuchten, die
    # gerade nicht dran sind. Ohne Boden waere es kein Atmen, sondern
    # ein Blitzen.
    #
    motor.puls = 0.0

    leer = motor.werte_je_lampe()["bar"]

    assert leer[0] == fixtures.begrenzen(255 * motor.GRUNDHELLIGKEIT), (
        f"Zwischen den Schlägen muss der Boden stehen bleiben: {leer[:3]}"
    )

    assert voll[0] > leer[0] * 2, (
        f"Der Puls muss deutlich sichtbar sein: {voll[0]} gegen {leer[0]}"
    )

    print("OK: Zwischen den Schlägen bleibt die Grundhelligkeit stehen")

    #
    # Ohne Signal bleibt es auch bei vollem Puls dunkel. Der Puls
    # skaliert, was die Baender hergeben - er erfindet kein Licht.
    #
    motor.stand = {"low": 0.0, "mid": 0.0, "high": 0.0, "level": 0.0, "beat": False}
    motor.puls = 1.0

    assert set(motor.werte_je_lampe()["bar"]) == {0}, (
        motor.werte_je_lampe()["bar"]
    )

    print("OK: Auch im Puls-Modus bleibt es ohne Signal dunkel")


# --- Der einzelne RGB-Strahler --------------------------------------
#
# Der wandernde Punkt braucht mehrere Segmente, ueber die er wandern
# kann - eine Lampe mit einer einzigen Farbgruppe laesst er aus. Genau
# die profitiert vom Puls.

with tempfile.TemporaryDirectory() as tmp:

    licht = ablage(Path(tmp))
    licht.set_enabled(True)
    licht.lampe_speichern({
        "id": "par", "name": "Par", "template": "rgb", "address": 1,
    })

    motor = LichtApp(licht, DmxAttrappe()).light_engine

    motor.stand = {"low": 1.0, "mid": 0.0, "high": 0.0, "level": 1.0, "beat": False}

    grund = {
        "sensitivity": 1.0,
        "color_low": "#ff0000",
        "color_mid": "#00ff00",
        "color_high": "#0000ff",
    }

    motor.einstellungen = dict(grund)

    motor.puls = 1.0
    mit = motor.werte_je_lampe()["par"][0]

    motor.puls = 0.0
    ohne = motor.werte_je_lampe()["par"][0]

    assert mit == ohne, (
        "Im Lauflicht darf der Puls nichts tun - sonst wirkt der Modus, "
        f"der gar nicht eingestellt ist: {mit} gegen {ohne}"
    )

    motor.einstellungen = {**grund, "effect_mode": "pulse"}

    motor.puls = 1.0
    mit = motor.werte_je_lampe()["par"][0]

    motor.puls = 0.0
    ohne = motor.werte_je_lampe()["par"][0]

    assert mit > ohne, (
        f"Der Puls muss auch einen einzelnen Strahler bewegen: {mit} gegen {ohne}"
    )

    print("OK: Der Puls wirkt auch auf Lampen ohne Segmente")


# --- Das Hintergrundlicht bleibt ein Wash ---------------------------

with tempfile.TemporaryDirectory() as tmp:

    licht = ablage(Path(tmp))
    licht.set_enabled(True)
    licht.lampe_speichern({
        "id": "wash", "name": "Wash", "template": "bar-8-rgb", "address": 1,
        "kind": "background",
    })

    motor = LichtApp(licht, DmxAttrappe()).light_engine

    motor.stand = {"low": 1.0, "mid": 0.5, "high": 0.2, "level": 1.0, "beat": False}

    grund = {
        "sensitivity": 1.0,
        "color_low_1": "#ff0000",
        "color_mid_1": "#00ff00",
        "color_high_1": "#0000ff",
        "background_seconds": 4.0,
    }

    #
    # Derselbe Augenblick in beiden Modi - und jedes Mal von vorn,
    # damit die Glaettung nicht das Ergebnis traegt.
    #
    motor.einstellungen = dict(grund)
    motor._hintergrund.clear()
    motor.puls = 0.0
    lauflicht = motor.werte_je_lampe()["wash"]

    #
    # BEIDE Enden der Huellkurve pruefen. Nur mit vollem Puls zu
    # messen faellt auf die Nase: Bei puls = 1.0 ist die Staerke
    # ohnehin 1.0, also genau der Wert, den das Hintergrundlicht
    # sowieso bekommt - ein durchgeschlagener Puls waere unsichtbar.
    # Genau daran ist die Gegenprobe zuerst vorbeigelaufen.
    #
    for stand_puls in (0.0, 0.5, 1.0):

        motor.einstellungen = {**grund, "effect_mode": "pulse"}
        motor._hintergrund.clear()
        motor.puls = stand_puls

        puls = motor.werte_je_lampe()["wash"]

        assert lauflicht == puls, (
            f"Das Hintergrundlicht darf vom Puls nichts mitbekommen "
            f"(puls={stand_puls}): {lauflicht[:6]} gegen {puls[:6]}"
        )

    print("OK: Der Puls lässt das Hintergrundlicht in Ruhe")


# --- Nachleuchten und Boden sind einstellbar ------------------------
#
# Beide Zahlen waren geraten. Ob sie stimmen, entscheidet sich an den
# Lampen und am Musikgeschmack - also gehoeren sie in die
# Einstellungen.

with tempfile.TemporaryDirectory() as tmp:

    licht = ablage(Path(tmp))
    licht.set_enabled(True)
    licht.lampe_speichern({
        "id": "par", "name": "Par", "template": "rgb", "address": 1,
    })

    motor = LichtApp(licht, DmxAttrappe()).light_engine

    #
    # Nachleuchten: Nach derselben Zeit ohne Schlag muss vom langen
    # Puls mehr uebrig sein als vom kurzen.
    #
    def nach_fuenf_bloecken(sekunden=None) -> float:

        motor.einstellungen = {"effect_mode": "pulse"}

        if sekunden is not None:
            motor.einstellungen["pulse_seconds"] = sekunden

        motor.puls = 1.0

        for _ in range(5):
            motor._puls_weiterschalten(0.02, False)

        return motor.puls

    kurz = nach_fuenf_bloecken(0.05)
    lang = nach_fuenf_bloecken(1.0)

    assert lang > kurz * 2, (
        f"Das Nachleuchten wirkt nicht: kurz {kurz:.3f}, lang {lang:.3f}"
    )

    #
    # Ohne Angabe bleibt es bei der Zahl, mit der der Puls gebaut
    # wurde - eine alte Einrichtung sieht genau wie vorher aus.
    #
    ohne = nach_fuenf_bloecken()

    erwartet = (1.0 - 0.02 / motor.PULS_ABFALL_S) ** 5

    assert abs(ohne - erwartet) < 0.001, (
        f"Ohne Einstellung muss PULS_ABFALL_S gelten: {ohne:.3f} statt "
        f"{erwartet:.3f}"
    )

    print("OK: Das Nachleuchten des Pulses ist einstellbar")

    #
    # Der Boden: was zwischen zwei Schlaegen stehen bleibt.
    #
    motor.stand = {"low": 1.0, "mid": 0.0, "high": 0.0, "level": 1.0, "beat": False}

    grund = {
        "sensitivity": 1.0,
        "color_low": "#ff0000",
        "color_mid": "#00ff00",
        "color_high": "#0000ff",
        "effect_mode": "pulse",
    }

    def rot(boden=None, puls=0.0) -> int:

        motor.einstellungen = dict(grund)

        if boden is not None:
            motor.einstellungen["pulse_base"] = boden

        motor.puls = puls

        return motor.werte_je_lampe()["par"][0]

    assert rot(0.8) > rot(), f"Ein hoher Boden muss heller sein: {rot(0.8)}"

    #
    # Und der linke Anschlag: 0 heisst "zwischen den Schlaegen ganz
    # aus". Genau der Wert faellt durch, wenn ihn jemand mit "or"
    # abfragt - dann waere er still die Vorgabe, und der Regler taete
    # am Anschlag nichts.
    #
    assert rot(0.0) == 0, (
        f"Boden 0 muss die Lampe zwischen den Schlägen ausmachen: {rot(0.0)}"
    )

    assert rot(0.0, puls=1.0) == 255, (
        "Auf dem Schlag muss auch mit Boden 0 voll aufgedreht werden: "
        f"{rot(0.0, puls=1.0)}"
    )

    #
    # Ohne Angabe die alte Zahl.
    #
    assert rot() == fixtures.begrenzen(255 * motor.GRUNDHELLIGKEIT), rot()

    print("OK: Die Grundhelligkeit des Pulses ist einstellbar, auch auf 0")

    #
    # Der wandernde Punkt bleibt davon unberuehrt. Er hat seine
    # eigene, feste Grundhelligkeit - sonst verstellte ein Regler,
    # der nur beim Puls dasteht, heimlich auch das andere Bild.
    #
    # Geprueft an einer Bar: Beim einzelnen Strahler leuchtet im
    # Lauflicht ohnehin alles voll, ein durchgeschlagener Boden waere
    # dort gar nicht zu sehen. Es braucht ein Segment, das gerade
    # NICHT dran ist.
    #
    licht.lampe_speichern({
        "id": "bar", "name": "Bar", "template": "bar-8-rgb", "address": 10,
    })

    motor.stand = {"low": 1.0, "mid": 1.0, "high": 1.0, "level": 1.0, "beat": False}

    motor.einstellungen = {
        **grund, "effect_mode": "runner", "pulse_base": 0.0,
        "pulse_seconds": 2.0,
    }
    motor.puls = 0.0
    motor.position = 0

    werte = motor.werte_je_lampe()["bar"]

    assert werte[0] == 255, f"Das Segment, das dran ist, muss voll sein: {werte[:9]}"

    assert werte[4] == fixtures.begrenzen(255 * motor.GRUNDHELLIGKEIT), (
        "Im Lauflicht dürfen die Puls-Regler nichts ändern: "
        f"{werte[3:6]}"
    )

    print("OK: Die Puls-Regler lassen den wandernden Punkt in Ruhe")


# --- Die Ablage -----------------------------------------------------

with tempfile.TemporaryDirectory() as tmp:

    licht = ablage(Path(tmp))

    #
    # Die Vorgaben muessen zu den Zahlen im Motor passen. Laufen sie
    # auseinander, sieht eine frische Einrichtung anders aus als eine
    # alte ohne die Schluessel - und niemand kaeme darauf, warum.
    #
    from lighting.light_engine import LightEngine

    assert licht.show_einstellungen()["pulse_seconds"] == LightEngine.PULS_ABFALL_S
    assert licht.show_einstellungen()["pulse_base"] == LightEngine.GRUNDHELLIGKEIT

    #
    # Unsinnige Werte werden gekappt, nicht abgewiesen: Ein Regler
    # kann gar nichts anderes liefern als eine Zahl, und wer per Hand
    # etwas schickt, soll dabei nicht die ganze Show anhalten.
    #
    licht.set_show_einstellungen({"pulse_seconds": 99.0, "pulse_base": 5.0})

    assert licht.show_einstellungen()["pulse_seconds"] == 2.0
    assert licht.show_einstellungen()["pulse_base"] == 0.9

    licht.set_show_einstellungen({"pulse_seconds": 0.0, "pulse_base": -1.0})

    assert licht.show_einstellungen()["pulse_seconds"] == 0.05
    assert licht.show_einstellungen()["pulse_base"] == 0.0

    print("OK: Nachleuchten und Boden werden in Grenzen gehalten")

    assert licht.show_einstellungen()["effect_mode"] == "runner", (
        "Vorgabe muss das bisherige Bild sein - wer nichts umstellt, "
        "soll nichts umgestellt bekommen."
    )

    ok, meldung = licht.set_show_einstellungen({"effect_mode": "pulse"})

    assert ok, meldung
    assert licht.show_einstellungen()["effect_mode"] == "pulse"

    #
    # Ein unbekannter Modus waere ein stiller Ausfall: Die Show fiele
    # auf das Lauflicht zurueck, und man suchte den Fehler bei den
    # Lampen.
    #
    ok, meldung = licht.set_show_einstellungen({"effect_mode": "disko"})

    assert not ok and "Modus" in meldung, meldung
    assert licht.show_einstellungen()["effect_mode"] == "pulse", (
        "Ein abgewiesener Wert darf den gespeicherten nicht anfassen."
    )

    print("OK: Der Modus wird gespeichert und auf bekannte Werte geprüft")


# ====================================================================
# 21. Der Blitz auf die Snare
#
# Die Show hat die Strobe-Kanaele bis hierhin nie angefasst. Das
# bleibt auch so - AUSSER jemand schaltet es ausdruecklich ein.
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    licht = ablage(Path(tmp))
    licht.set_enabled(True)
    licht.vorlage_speichern({
        "id": "spot", "name": "Spot mit Strobe",
        "channels": ["red", "green", "blue", "strobe"],
    })
    licht.lampe_speichern({
        "id": "s", "name": "Spot", "template": "spot", "address": 1,
    })

    app = LichtApp(licht, DmxAttrappe())
    motor = app.light_engine

    motor.stand = {"low": 1.0, "mid": 0.5, "high": 0.5, "level": 1.0,
                   "beat": False, "snare": False}

    grund = {
        "sensitivity": 1.0,
        "color_low": "#ff0000",
        "color_mid": "#00ff00",
        "color_high": "#0000ff",
    }

    #
    # Ausgeschaltet: Ein von Hand gestellter Strobe-Wert bleibt
    # stehen, auch mitten im Blitz. Das ist die Zusicherung, die es
    # schon vorher gab.
    #
    motor.einstellungen = dict(grund)
    app.light_values["s"] = [0, 0, 0, 111]
    motor.blitz = motor.BLITZ_DAUER_S

    assert motor.werte_je_lampe()["s"][3] == 111, (
        "Ohne eingeschalteten Blitz darf die Show den Strobe-Kanal nicht "
        f"anfassen: {motor.werte_je_lampe()['s']}"
    )

    print("OK: Ohne Blitz bleibt der Strobe-Kanal, wo er ist")

    #
    # Eingeschaltet: Waehrend des Blitzes steht der Wert da...
    #
    motor.einstellungen = {**grund, "snare_strobe": True, "snare_power": 0.8}

    werte = motor.werte_je_lampe()["s"]

    assert werte[3] == fixtures.begrenzen(255 * 0.8), (
        f"Der Blitz kommt nicht an: {werte}"
    )

    #
    # ... und danach wieder 0.
    #
    # Das ist die Stelle, an der es leicht schiefgeht: Jedes Bild
    # beginnt bei dem, was zuletzt drin stand. Wuerde die Show den
    # Kanal nach dem Blitz einfach "in Ruhe lassen", bliebe der
    # Blitzwert stehen - und das Strobe liefe durch, bis jemand die
    # Show anhaelt.
    #
    app.light_values["s"] = werte
    motor.blitz = 0.0

    assert motor.werte_je_lampe()["s"][3] == 0, (
        "Nach dem Blitz muss der Strobe-Kanal wieder auf 0 - sonst läuft "
        f"das Strobe durch: {motor.werte_je_lampe()['s']}"
    )

    print("OK: Der Blitz kommt und geht auch wieder")

    #
    # Die Staerke ist einstellbar, und 0 heisst 0 - kein stiller
    # Rueckfall auf die Vorgabe.
    #
    motor.blitz = motor.BLITZ_DAUER_S

    motor.einstellungen = {**grund, "snare_strobe": True, "snare_power": 0.4}
    assert motor.werte_je_lampe()["s"][3] == fixtures.begrenzen(255 * 0.4)

    motor.einstellungen = {**grund, "snare_strobe": True, "snare_power": 0.0}
    assert motor.werte_je_lampe()["s"][3] == 0, (
        "Stärke 0 muss 0 bedeuten und nicht die Vorgabe."
    )

    #
    # Ohne Angabe die eingebaute Staerke.
    #
    motor.einstellungen = {**grund, "snare_strobe": True}
    assert motor.werte_je_lampe()["s"][3] == fixtures.begrenzen(
        255 * motor.BLITZ_STAERKE
    )

    print("OK: Die Stärke des Blitzes ist einstellbar, auch auf 0")

    #
    # Der Blitz laeuft ab, und ein neuer Schlag setzt ihn zurueck.
    #
    motor.blitz = 0.0
    motor._blitz_weiterschalten(0.02, True)

    assert motor.blitz == motor.BLITZ_DAUER_S, motor.blitz

    for _ in range(int(motor.BLITZ_DAUER_S / 0.02) + 1):
        motor._blitz_weiterschalten(0.02, False)

    assert motor.blitz == 0.0, (
        f"Der Blitz muss von selbst ablaufen: {motor.blitz}"
    )

    #
    # Und er wird nie negativ - sonst waere die Bedingung "> 0"
    # zwar noch richtig, aber die Zahl waeche ins Bodenlose.
    #
    for _ in range(100):
        motor._blitz_weiterschalten(0.02, False)

    assert motor.blitz == 0.0, motor.blitz

    print("OK: Der Blitz läuft ab und ein neuer Schlag setzt ihn zurück")


# --- Der Motor loest den Blitz auch wirklich aus --------------------

with tempfile.TemporaryDirectory() as tmp:

    from lighting.analysis import Stimmungserkennung

    class SnareAttrappe:
        """Liefert einen festen Analysestand mit oder ohne Snare."""

        rate = 48000
        channels = 2

        def __init__(self, snare: bool):
            self.snare = snare

        def verarbeite(self, block):
            return {"low": 0.5, "mid": 0.5, "high": 0.5,
                    "level": 0.5, "beat": False, "snare": self.snare}

    licht = ablage(Path(tmp))
    licht.set_enabled(True)

    motor = LichtApp(licht, DmxAttrappe()).light_engine

    motor.erkennung = Stimmungserkennung(
        stille_schwelle=0.002, stille_sekunden=6.0, sprache_sekunden=0.0
    )
    motor.einstellungen = {"sensitivity": 1.0, "snare_strobe": True}

    block = bytes(int(0.02 * 2 * 4 * 48000))

    motor.blitz = 0.0
    motor.analyse = SnareAttrappe(True)
    motor._schritt(block)

    assert motor.blitz == motor.BLITZ_DAUER_S, (
        f"Eine Snare im Betrieb muss den Blitz auslösen: {motor.blitz}"
    )

    motor.analyse = SnareAttrappe(False)

    for _ in range(10):
        motor._schritt(block)

    assert motor.blitz == 0.0, (
        f"Ohne Snare muss der Blitz im Betrieb ablaufen: {motor.blitz}"
    )

    print("OK: Der Show-Thread löst den Blitz auf die Snare aus")


# --- Das Hintergrundlicht blitzt nicht ------------------------------

with tempfile.TemporaryDirectory() as tmp:

    licht = ablage(Path(tmp))
    licht.set_enabled(True)
    licht.vorlage_speichern({
        "id": "spot2", "name": "Spot mit Strobe",
        "channels": ["red", "green", "blue", "strobe"],
    })
    licht.lampe_speichern({
        "id": "w", "name": "Wash", "template": "spot2", "address": 1,
        "kind": "background",
    })

    app = LichtApp(licht, DmxAttrappe())
    motor = app.light_engine

    motor.stand = {"low": 1.0, "mid": 0.5, "high": 0.5, "level": 1.0,
                   "beat": False, "snare": False}
    motor.einstellungen = {
        "sensitivity": 1.0, "snare_strobe": True,
        "color_low_1": "#ff0000", "color_mid_1": "#00ff00",
        "color_high_1": "#0000ff",
    }

    app.light_values["w"] = [0, 0, 0, 77]
    motor.blitz = motor.BLITZ_DAUER_S

    assert motor.werte_je_lampe()["w"][3] == 77, (
        "Ein Wash, in den ein Blitz hineinfährt, ist kein Wash mehr: "
        f"{motor.werte_je_lampe()['w']}"
    )

    print("OK: Das Hintergrundlicht blitzt nicht mit")


# --- Die Ablage -----------------------------------------------------

with tempfile.TemporaryDirectory() as tmp:

    licht = ablage(Path(tmp))

    #
    # Aus als Vorgabe, und das ist keine Geschmacksfrage: Ein
    # Blitzlicht, das nach einem Update von selbst angeht, will
    # niemand.
    #
    assert licht.show_einstellungen()["snare_strobe"] is False, (
        "Der Blitz muss ausgeschaltet vorgegeben sein."
    )

    from lighting.light_engine import LightEngine
    from lighting.analysis import SNARE_SCHWELLE

    assert licht.show_einstellungen()["snare_threshold"] == SNARE_SCHWELLE
    assert licht.show_einstellungen()["snare_power"] == LightEngine.BLITZ_STAERKE

    ok, meldung = licht.set_show_einstellungen({"snare_strobe": True})

    assert ok, meldung
    assert licht.show_einstellungen()["snare_strobe"] is True

    licht.set_show_einstellungen({"snare_threshold": 9.0, "snare_power": 9.0})

    assert licht.show_einstellungen()["snare_threshold"] == 0.9
    assert licht.show_einstellungen()["snare_power"] == 1.0

    licht.set_show_einstellungen({"snare_threshold": 0.0, "snare_power": -1.0})

    assert licht.show_einstellungen()["snare_threshold"] == 0.2
    assert licht.show_einstellungen()["snare_power"] == 0.0

    print("OK: Der Blitz ist aus als Vorgabe, seine Werte bleiben in Grenzen")


print("Alle Licht-Tests erfolgreich.")
