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
#
# Die beiden Bilder, in denen die Show Effektlicht faehrt.
#
#   runner - der wandernde Punkt: ein Segment leuchtet voll, die
#            uebrigen mit Grundhelligkeit, weitergerueckt bei jedem
#            Schlag.
#   pulse  - alles atmet im Takt: jedes Segment behaelt seine
#            Bandfarbe, bei jedem Schlag gehen alle auf voll und
#            fallen bis zum naechsten zurueck.
#
# Hintergrundlicht ist davon nicht betroffen - ein Wash soll weder
# wandern noch zucken.
#
EFFEKT_MODI = ("runner", "pulse")

SHOW_VORGABE = {
    #
    # 1-basierter linker Kanal des Paares, das die Show hoert.
    #
    "channel": 1,
    "sensitivity": 1.0,

    #
    # Welches Bild das Effektlicht faehrt. Vorgabe ist der bisherige
    # Zustand: Wer nichts umstellt, sieht genau das von vorher.
    #
    "effect_mode": "runner",

    #
    # Die beiden Schrauben am Puls. Vorgaben sind genau die Zahlen,
    # mit denen er gebaut wurde - wer nichts anfasst, sieht das Bild
    # von vorher.
    #
    # Wie lange ein Schlag nachleuchtet, in Sekunden: die
    # Zeitkonstante, mit der die Huellkurve zurueckfaellt.
    #
    "pulse_seconds": 0.25,

    #
    # Wie hell es zwischen zwei Schlaegen bleibt (0-1). 0 heisst
    # "dazwischen ganz aus" - ein hartes Bild, aber eines, das jemand
    # wollen kann.
    #
    "pulse_base": 0.35,

    #
    # Blitz auf die Snare.
    #
    # AUS als Vorgabe, und das bleibt auch so: Ein Blitzlicht, das
    # nach einem Update von selbst angeht, will niemand - und wer es
    # nicht ausdruecklich einschaltet, dem fasst die Show die
    # Strobe-Kanaele weiterhin gar nicht an.
    #
    "snare_strobe": False,

    #
    # Ab wie laut. Anteil an der laufenden Spitze; hoeher heisst,
    # dass nur noch die groessten Schlaege durchkommen.
    #
    "snare_threshold": 0.7,

    #
    # Was waehrend des Blitzes auf dem Strobe-Kanal steht (0-1 von
    # 255). Was der Wert am Geraet bewirkt - Helligkeit oder
    # Blitzgeschwindigkeit -, steht in keiner Norm, sondern in der
    # Tabelle des jeweiligen Geraets. Deshalb ein Regler.
    #
    "snare_power": 0.8,

    #
    # Welche Farbe welches Band bekommt.
    #
    # Vorgabe ist die uebliche Zuordnung von Sound-to-Light-Geraeten
    # (tief rot, mittel gruen, hoch blau) - aber das ist Geschmack,
    # nicht Physik. Wer eine Buehne in Blau und Gold will, soll das
    # einstellen koennen, ohne dass jemand am Programm etwas aendert.
    #
    "color_low": "#ff0000",
    "color_mid": "#00ff00",
    "color_high": "#0000ff",

    #
    # Derselbe Satz noch einmal fuer die ERSTE Hintergrundgruppe.
    #
    # Die Vorgabe ist mit Absicht dieselbe wie oben: Wer nichts
    # umstellt, sieht genau das Bild von vorher, als sich Effektlicht
    # und Hintergrund 1 noch einen Satz teilten. Es geht erst
    # auseinander, wenn man es auseinanderzieht.
    #
    "color_low_1": "#ff0000",
    "color_mid_1": "#00ff00",
    "color_high_1": "#0000ff",

    #
    # Und fuer die zweite Hintergrundgruppe.
    #
    # Die Vorgabe ist bewusst eine ANDERE Palette - Magenta, Amber,
    # Cyan statt Rot, Gruen, Blau. Waeren beide gleich, saehe man den
    # Unterschied zwischen den Gruppen erst, nachdem man selbst
    # etwas umgestellt hat, und haette bis dahin den Eindruck, die
    # zweite Gruppe tue nichts.
    #
    "color_low_2": "#ff00ff",
    "color_mid_2": "#ffaa00",
    "color_high_2": "#00ffff",

    #
    # Szene, auf die bei Sprache oder Stille umgeschaltet wird.
    # Leer heisst: dann geht das Licht aus.
    #
    "fallback_scene": "",

    #
    # Stille-Schwelle als linearer RMS-Wert. 0.002 sind rund
    # -54 dBFS.
    #
    # Vorher standen hier 0.02, also -34 dBFS - und das war schlicht
    # falsch gedacht. Ein normaler Ausspielweg vom Pult liegt weit
    # darunter; erst mit dem Kanal auf 0 dB kam das Signal darueber.
    # Die Show hielt also normal laufende Musik fuer Stille und
    # schaltete nach sechs Sekunden auf die Rueckfallszene. Genau das
    # war am Geraet zu sehen.
    #
    "silence_threshold": 0.002,
    "silence_seconds": 6.0,

    #
    # 0 heisst: Spracherkennung aus. Siehe die Begruendung in
    # lighting/analysis.py (Stimmungserkennung) - "kein Bassschlag"
    # ist kein Beweis fuer eine Ansage, und ein Fehlgriff mitten im
    # Stueck ist schlimmer als gar keine Erkennung.
    #
    "speech_seconds": 0.0,

    #
    # Wie traege das Hintergrundlicht der Musik folgt, in Sekunden.
    #
    # Vier Sekunden sind so gewaehlt, dass ein Wash einem Wechsel der
    # Stimmung noch folgt, aber keinem einzelnen Schlag mehr. Kuerzer
    # waere es wieder Effektlicht, laenger merkt man den Bezug zur
    # Musik nicht mehr.
    #
    "background_seconds": 4.0,

    #
    # Nach wie vielen Schlaegen das Hintergrundlicht die naechste
    # Farbe nimmt. 16 sind bei 120 BPM rund vier Takte.
    #
    "background_beats": 16,

    #
    # Wie lange das Ausblenden in die Rueckfallszene dauert.
    #
    # 0 ist mit Absicht erlaubt und bedeutet hartes Umschalten - so
    # war es vorher, und wer den Schnitt will, soll ihn bekommen.
    #
    "fade_seconds": 2.0,
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

        #
        # Fehlt die Art, gilt "effect". Damit lesen Oberflaeche und
        # Show bei einer Einrichtung aus einer aelteren Fassung
        # dasselbe, ohne dass die Ablage einmal umgeschrieben werden
        # muesste - ein Wanderungsschritt, der schiefgehen kann, fuer
        # eine Vorgabe, die man auch beim Lesen setzen kann.
        #
        return [
            {"kind": fixtures.ART_VORGABE, **lampe}
            for lampe in self._laden()["fixtures"]
        ]

    def lampe_speichern(self, lampe: dict) -> tuple[bool, str]:
        """Eine Lampe anlegen oder ändern."""

        lampe = {
            "id": str(lampe.get("id") or self._kennung()),
            "name": str(lampe.get("name", "")).strip(),
            "template": str(lampe.get("template", "")),
            "address": lampe.get("address"),
            "kind": str(lampe.get("kind") or fixtures.ART_VORGABE),
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

        #
        # Kein zweites Mal derselbe Name.
        #
        # Szenen werden ueberall ueber ihren Namen ausgewaehlt - in
        # der Karte und in der Rueckfall-Auswahl. Zwei Szenen "Pause"
        # sind dort nicht auseinanderzuhalten: Man klickt eine und
        # bekommt vielleicht die andere.
        #
        # Die eigene Szene muss ausgenommen bleiben. Diese Funktion
        # legt naemlich nicht nur an, sie aendert auch - und eine
        # vorhandene Szene unter ihrem eigenen Namen zu speichern
        # duerfte nicht plötzlich scheitern.
        #
        for vorhanden in daten["scenes"]:

            if vorhanden.get("id") == kennung:
                continue

            if str(vorhanden.get("name", "")).strip().lower() == name.lower():
                return False, "Eine Szene mit diesem Namen gibt es schon.", ""

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

        farbnamen = tuple(
            f"color_{band}{satz}"
            for satz in ("", "_1", "_2")
            for band in ("low", "mid", "high")
        )

        for name in farbnamen:

            if name not in werte:
                continue

            farbe = str(werte[name] or "").strip().lower()

            #
            # Nur "#rrggbb". Was hier durchrutscht, landet spaeter in
            # einer Rechnung und faerbt entweder gar nichts oder alles
            # falsch - und man sucht den Fehler in der Analyse.
            #
            if (len(farbe) != 7 or not farbe.startswith("#")
                    or any(z not in "0123456789abcdef" for z in farbe[1:])):
                return False, f"'{werte[name]}' ist keine gültige Farbe."

            show[name] = farbe

        if "effect_mode" in werte:

            modus = str(werte["effect_mode"] or "").strip().lower()

            #
            # Ein unbekannter Modus waere ein stiller Ausfall: Die
            # Show faellt auf das Lauflicht zurueck, und man sucht
            # den Fehler bei den Lampen.
            #
            if modus not in EFFEKT_MODI:
                return False, f"'{werte['effect_mode']}' ist kein bekannter Modus."

            show["effect_mode"] = modus

        if "sensitivity" in werte:
            show["sensitivity"] = max(0.1, min(4.0, float(werte["sensitivity"])))

        #
        # Unter 0,05 s waere der Puls kuerzer als der Abstand zweier
        # Bloecke (rund 20 ms) und damit gar nicht mehr darstellbar;
        # ueber zwei Sekunden stuende er bei jedem Tempo dauerhaft
        # oben.
        #
        if "pulse_seconds" in werte:
            show["pulse_seconds"] = max(
                0.05, min(2.0, float(werte["pulse_seconds"]))
            )

        #
        # Nach oben bei 0,9 Schluss: Bei 1,0 gaebe es ueberhaupt
        # keinen Puls mehr. Ein Regler, der genau den Effekt
        # abschaltet, den er einstellen soll, hoert vorher auf.
        #
        if "pulse_base" in werte:
            show["pulse_base"] = max(0.0, min(0.9, float(werte["pulse_base"])))

        if "snare_strobe" in werte:
            show["snare_strobe"] = bool(werte["snare_strobe"])

        #
        # Unter 0,2 spraeche fast jeder Einsatz an, ueber 0,9 nur
        # noch der eine lauteste Moment eines Stuecks.
        #
        if "snare_threshold" in werte:
            show["snare_threshold"] = max(
                0.2, min(0.9, float(werte["snare_threshold"]))
            )

        if "snare_power" in werte:
            show["snare_power"] = max(
                0.0, min(1.0, float(werte["snare_power"]))
            )

        if "background_seconds" in werte:
            show["background_seconds"] = max(
                1.0, min(15.0, float(werte["background_seconds"]))
            )

        if "fade_seconds" in werte:
            show["fade_seconds"] = max(
                0.0, min(10.0, float(werte["fade_seconds"]))
            )

        if "background_beats" in werte:
            show["background_beats"] = max(
                1, min(64, int(werte["background_beats"]))
            )

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
            #
            # 0 ist erlaubt und heisst "aus".
            #
            show["speech_seconds"] = max(0.0, min(300.0, float(werte["speech_seconds"])))

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

        #
        # Zu jeder Lampe auch den letzten belegten Kanal. Ausrechnen
        # koennte die Oberflaeche das selbst, aber dann stuende die
        # Regel an zwei Stellen - und die Ueberschneidungspruefung
        # weiter unten benutzt schon dieselbe Funktion. Nebenbei
        # nimmt es dem Nutzer das Kopfrechnen ab, wenn er die
        # naechste Lampe adressieren will.
        #
        mit_bereich = []

        for lampe in lampen:

            if lampe.get("template") in vorlagen:
                _, ende = fixtures.adressbereich(lampe, vorlagen)
                mit_bereich.append({**lampe, "last_address": ende})
            else:
                mit_bereich.append(dict(lampe))

        return {
            "enabled": self.enabled,
            "templates": list(vorlagen.values()),
            "fixtures": mit_bereich,
            "scenes": self.szenen(),
            "roles": list(fixtures.ROLLEN),
            "overlaps": fixtures.ueberschneidungen(lampen, vorlagen),
            "show": self.show_einstellungen(),
        }
