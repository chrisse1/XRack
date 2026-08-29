"""
Ablage der Lichteinrichtung: Vorlagen, Lampen, Szenen.

Alles liegt unter einem einzigen Schlüssel im StateStore
(config/state.json). Ein Schlüssel und nicht drei, weil der
StateStore die ganze Datei auf einmal schreibt: Bei drei Schlüsseln
gäbe es Augenblicke, in denen die Lampen schon neu sind und die
Szenen noch alt - und eine Szene, die auf eine gelöschte Lampe zeigt,
ist genau die Art von Zustand, den man nie wieder los wird.

Warum hier und nicht in config/default.yaml: Das dortige Schema kennt
nur einzelne Werte (Port, Sprache, Abtastrate). Listen mit Struktur,
die der Nutzer im Betrieb ändert, gehören in den StateStore - so wie
die gekoppelten Kanalpaare in core/application/pult.py.
"""

import logging
from uuid import uuid4

from lighting import fixtures


#
# Vorgaben der musikgesteuerten Show.
#
# Die Schwellen der Stimmungserkennung stehen bewusst hier und nicht
# fest im Code: Ob eine leise Stelle noch Musik ist oder schon eine
# Ansage, haengt vom Signal ab, das vor Ort ankommt. Nachjustieren
# muss ohne Codeaenderung gehen.
#
SHOW_VORGABE = {
    #
    # 1-basierter linker Kanal des Paares, das die Show hoert.
    #
    "channel": 1,
    "sensitivity": 1.0,

    #
    # Szene, auf die bei Sprache oder Stille umgeschaltet wird.
    # Leer heisst: dann geht das Licht aus.
    #
    "fallback_scene": "",

    "silence_threshold": 0.02,
    "silence_seconds": 6.0,
    "speech_seconds": 12.0,
}


class LightingStore:
    """Liest und schreibt die Lichteinrichtung."""

    SCHLUESSEL = "dmx_config"

    def __init__(self, state_store):

        self.state_store = state_store
        self.logger = logging.getLogger("XRack")

    # ----------------------------------------------------------------
    # Grundlage
    # ----------------------------------------------------------------

    def _laden(self) -> dict:
        """Der gespeicherte Stand, mit brauchbaren Vorgaben."""

        daten = self.state_store.get(self.SCHLUESSEL) or {}

        if not isinstance(daten, dict):
            daten = {}

        return {
            "enabled": bool(daten.get("enabled", False)),
            "templates": list(daten.get("templates") or []),
            "fixtures": list(daten.get("fixtures") or []),
            "scenes": list(daten.get("scenes") or []),
            "show": {**SHOW_VORGABE, **(daten.get("show") or {})},
        }

    def _sichern(self, daten: dict) -> None:

        self.state_store.set(self.SCHLUESSEL, daten)

    @staticmethod
    def _kennung() -> str:
        """Eine kurze, eindeutige Kennung."""

        return uuid4().hex[:8]

    # ----------------------------------------------------------------
    # An oder aus
    # ----------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        """
        Ob die Lichtsteuerung überhaupt benutzt wird.

        Standardmäßig aus: Wer kein DMX hat - also die meisten - soll
        die Karte gar nicht erst sehen.
        """

        return self._laden()["enabled"]

    def set_enabled(self, enabled: bool) -> None:

        daten = self._laden()
        daten["enabled"] = bool(enabled)

        self._sichern(daten)

    # ----------------------------------------------------------------
    # Vorlagen
    # ----------------------------------------------------------------

    def vorlagen(self) -> dict:
        """
        Alle Vorlagen als Kennung -> Vorlage, mitgelieferte zuerst.

        Eigene Vorlagen mit derselben Kennung wie eine mitgelieferte
        haben Vorrang: Wer eine eingebaute Vorlage anpasst, bekommt
        seine Fassung und nicht wieder unsere.
        """

        alle = {
            vorlage["id"]: vorlage
            for vorlage in fixtures.eingebaute_vorlagen()
        }

        for vorlage in self._laden()["templates"]:

            if isinstance(vorlage, dict) and vorlage.get("id"):
                alle[vorlage["id"]] = {**vorlage, "builtin": False}

        return alle

    def vorlage_speichern(self, vorlage: dict) -> tuple[bool, str]:
        """Eine eigene Vorlage anlegen oder ändern."""

        vorlage = {
            "id": str(vorlage.get("id") or self._kennung()),
            "name": str(vorlage.get("name", "")).strip(),
            "channels": list(vorlage.get("channels") or []),
            "builtin": False,
        }

        fehler = fixtures.pruefe_vorlage(vorlage)

        if fehler:
            return False, fehler

        daten = self._laden()

        daten["templates"] = [
            vorhanden for vorhanden in daten["templates"]
            if vorhanden.get("id") != vorlage["id"]
        ] + [vorlage]

        self._sichern(daten)

        return True, ""

    def vorlage_loeschen(self, kennung: str) -> tuple[bool, str]:
        """
        Eine eigene Vorlage entfernen.

        Nicht, solange eine Lampe sie benutzt - sonst stünden Lampen
        da, zu denen es keine Kanalbelegung mehr gibt, und die Szenen
        dazu wären still wertlos.
        """

        daten = self._laden()

        benutzt = [
            lampe["name"] for lampe in daten["fixtures"]
            if lampe.get("template") == kennung
        ]

        if benutzt:
            return False, (
                "Diese Vorlage wird noch benutzt von: " + ", ".join(benutzt)
            )

        uebrig = [
            vorlage for vorlage in daten["templates"]
            if vorlage.get("id") != kennung
        ]

        if len(uebrig) == len(daten["templates"]):
            return False, "Diese Vorlage lässt sich nicht löschen."

        daten["templates"] = uebrig

        self._sichern(daten)

        return True, ""

    # ----------------------------------------------------------------
    # Lampen
    # ----------------------------------------------------------------

    def lampen(self) -> list[dict]:

        return self._laden()["fixtures"]

    def lampe_speichern(self, lampe: dict) -> tuple[bool, str]:
        """Eine Lampe anlegen oder ändern."""

        lampe = {
            "id": str(lampe.get("id") or self._kennung()),
            "name": str(lampe.get("name", "")).strip(),
            "template": str(lampe.get("template", "")),
            "address": lampe.get("address"),
        }

        fehler = fixtures.pruefe_lampe(lampe, self.vorlagen())

        if fehler:
            return False, fehler

        lampe["address"] = int(lampe["address"])

        daten = self._laden()

        daten["fixtures"] = [
            vorhanden for vorhanden in daten["fixtures"]
            if vorhanden.get("id") != lampe["id"]
        ] + [lampe]

        self._sichern(daten)

        return True, ""

    def lampe_loeschen(self, kennung: str) -> tuple[bool, str]:
        """
        Eine Lampe entfernen - und ihre Werte aus allen Szenen gleich
        mit.

        Bliebe sie in den Szenen stehen, käme sie beim Anlegen einer
        gleichnamigen Lampe unter Umständen mit alten Werten zurück.
        """

        daten = self._laden()

        uebrig = [
            lampe for lampe in daten["fixtures"]
            if lampe.get("id") != kennung
        ]

        if len(uebrig) == len(daten["fixtures"]):
            return False, "Diese Lampe gibt es nicht."

        daten["fixtures"] = uebrig

        for szene in daten["scenes"]:
            szene.get("values", {}).pop(kennung, None)
            szene.get("brightness", {}).pop(kennung, None)

        self._sichern(daten)

        return True, ""

    # ----------------------------------------------------------------
    # Szenen
    # ----------------------------------------------------------------

    def szenen(self) -> list[dict]:

        return self._laden()["scenes"]

    def szene(self, kennung: str) -> dict | None:

        for szene in self.szenen():
            if szene.get("id") == kennung:
                return szene

        return None

    def szene_speichern(self, name: str, zustaende: dict,
                        kennung: str = "",
                        helligkeiten: dict | None = None) -> tuple[bool, str, str]:
        """
        Den übergebenen Zustand als Szene ablegen.

        Gespeichert werden die Werte je Lampe, relativ zu deren
        erstem Kanal - nicht als absolute DMX-Kanäle. Wer eine Lampe
        später auf eine andere Startadresse zieht, muss seine Szenen
        deshalb nicht neu bauen.

        Zurück kommt (Erfolg, Meldung, Kennung).
        """

        name = str(name).strip()

        if not name:
            return False, "Die Szene braucht einen Namen.", ""

        vorlagen = self.vorlagen()
        daten = self._laden()

        bekannt = {lampe["id"] for lampe in daten["fixtures"]}

        werte = {}

        for lampen_id, liste in (zustaende or {}).items():

            #
            # Nur bekannte Lampen: Was der Aufrufer sonst noch
            # mitschickt, hat in der Ablage nichts verloren.
            #
            if lampen_id not in bekannt:
                continue

            werte[lampen_id] = [fixtures.begrenzen(wert) for wert in liste]

        #
        # Die Helligkeit gehört mit in die Szene: Sie ist eine eigene
        # Größe und steckt nicht in den Werten (siehe fixtures.bild).
        # Ohne sie käme eine gespeicherte Stimmung beim Aufrufen mit
        # voller Helligkeit zurück.
        #
        licht = {
            lampen_id: fixtures.begrenzen(wert)
            for lampen_id, wert in (helligkeiten or {}).items()
            if lampen_id in bekannt
        }

        szene = {
            "id": str(kennung or self._kennung()),
            "name": name,
            "values": werte,
            "brightness": licht,
        }

        daten["scenes"] = [
            vorhanden for vorhanden in daten["scenes"]
            if vorhanden.get("id") != szene["id"]
        ] + [szene]

        self._sichern(daten)

        return True, "", szene["id"]

    def szene_loeschen(self, kennung: str) -> tuple[bool, str]:

        daten = self._laden()

        uebrig = [
            szene for szene in daten["scenes"]
            if szene.get("id") != kennung
        ]

        if len(uebrig) == len(daten["scenes"]):
            return False, "Diese Szene gibt es nicht."

        daten["scenes"] = uebrig

        self._sichern(daten)

        return True, ""

    # ----------------------------------------------------------------
    # Die musikgesteuerte Show
    # ----------------------------------------------------------------

    def show_einstellungen(self) -> dict:

        return self._laden()["show"]

    def set_show_einstellungen(self, werte: dict) -> tuple[bool, str]:
        """
        Die Einstellungen der Show aendern. Nur bekannte Schluessel,
        und alles in vernuenftigen Grenzen.
        """

        daten = self._laden()
        show = dict(daten["show"])

        if "channel" in werte:

            try:
                kanal = int(werte["channel"])
            except (TypeError, ValueError):
                return False, "Der Kanal muss eine Zahl sein."

            if kanal < 1:
                return False, "Der Kanal muss mindestens 1 sein."

            show["channel"] = kanal

        if "sensitivity" in werte:
            show["sensitivity"] = max(0.1, min(4.0, float(werte["sensitivity"])))

        if "fallback_scene" in werte:

            kennung = str(werte["fallback_scene"] or "")

            #
            # Eine Szene, die es nicht gibt, waere ein stiller
            # Ausfall: Bei Stille passierte dann einfach nichts.
            #
            if kennung and not any(
                szene.get("id") == kennung for szene in daten["scenes"]
            ):
                return False, "Diese Szene gibt es nicht."

            show["fallback_scene"] = kennung

        if "silence_threshold" in werte:
            show["silence_threshold"] = max(
                0.0, min(0.5, float(werte["silence_threshold"]))
            )

        if "silence_seconds" in werte:
            show["silence_seconds"] = max(1.0, min(120.0, float(werte["silence_seconds"])))

        if "speech_seconds" in werte:
            show["speech_seconds"] = max(1.0, min(300.0, float(werte["speech_seconds"])))

        daten["show"] = show

        self._sichern(daten)

        return True, ""

    # ----------------------------------------------------------------
    # Übersicht
    # ----------------------------------------------------------------

    def uebersicht(self) -> dict:
        """Alles, was die Oberfläche zum Anzeigen braucht."""

        vorlagen = self.vorlagen()
        lampen = self.lampen()

        return {
            "enabled": self.enabled,
            "templates": list(vorlagen.values()),
            "fixtures": lampen,
            "scenes": self.szenen(),
            "roles": list(fixtures.ROLLEN),
            "overlaps": fixtures.ueberschneidungen(lampen, vorlagen),
            "show": self.show_einstellungen(),
        }
