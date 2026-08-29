"""
Der Thread, der aus Musik Licht macht.

Aufbau der Kette:

    Recorder-Thread  --(Block)-->  Warteschlange  -->  dieser Thread
                                                        |
                                            Bandanalyse + Abbildung
                                                        |
                                                  DMX an olad

Die Trennung durch die Warteschlange ist der wichtigste Teil davon.
Der Recorder-Thread darf NICHTS Zeitaufwendiges tun - alles, was dort
länger dauert, verzögert das nächste Lesen von ALSA und riskiert
einen Überlauf, also verlorene Audiodaten mitten in einer Aufnahme.
Deshalb legt er den Block nur ab und ist fertig; gerechnet wird
hier.

Die Warteschlange ist bewusst winzig (zwei Plätze) und verwirft, wenn
sie voll ist. Kommt die Lichtberechnung einmal nicht hinterher, ist
ein ausgelassenes Lichtbild die richtige Antwort - Blöcke aufzustauen
hieße, dass das Licht der Musik immer weiter hinterherhinkt, und das
sieht schlimmer aus als ein übersprungener Moment.
"""

import logging
import math
import queue
import threading

from lighting import fixtures
from lighting.analysis import Bandanalyse, Stimmungserkennung

#
# Farbrollen in der Reihenfolge, in der die Bänder darauf abgebildet
# werden: tief -> rot, mittel -> grün, hoch -> blau.
#
# Das ist die übliche Zuordnung von Sound-to-Light-Geräten, und sie
# hat einen praktischen Grund: Bass ist das, was am kräftigsten
# schwankt, und Rot ist die Farbe, die am wenigsten blendet.
#
BAND_ZU_FARBE = (
    ("low", "red"),
    ("mid", "green"),
    ("high", "blue"),
)


class LightEngine:
    """Die musikgesteuerte Lichtshow."""

    #
    # Zwei Plaetze: einer in Arbeit, einer wartet. Mehr staut nur auf.
    #
    WARTESCHLANGE = 2

    #
    # Wie stark ein Segment leuchtet, das gerade nicht "dran" ist.
    # Ganz aus waere ein hartes Lauflicht; so bleibt ein Grundbild
    # stehen, ueber das der Punkt wandert.
    #
    GRUNDHELLIGKEIT = 0.35

    def __init__(self, application):

        self.application = application
        self.logger = logging.getLogger("XRack")

        self._queue: queue.Queue = queue.Queue(maxsize=self.WARTESCHLANGE)
        self._thread: threading.Thread | None = None
        self._laeuft = False

        self.analyse: Bandanalyse | None = None
        self.erkennung: Stimmungserkennung | None = None

        #
        # Der letzte Analysestand - fuer die Anzeige in der Karte.
        #
        self.stand: dict = {"low": 0.0, "mid": 0.0, "high": 0.0,
                            "level": 0.0, "beat": False}

        self.zustand = "music"

        #
        # Bis start() sie setzt: brauchbare Vorgaben, damit die
        # Abbildung auch ohne laufende Show aufrufbar bleibt.
        #
        self.einstellungen: dict = {}

        #
        # Wandernder Punkt fuer Geraete mit mehreren Segmenten, und
        # die Phase der Bewegung fuer Pan/Tilt.
        #
        self.position = 0
        self.phase = 0.0

        self.verworfen = 0

    # ----------------------------------------------------------------
    # An und aus
    # ----------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._laeuft

    def start(self, rate: int, channels: int,
              links: int, rechts: int, einstellungen: dict) -> None:
        """Die Show starten."""

        if self._laeuft:
            return

        self.analyse = Bandanalyse(
            rate=rate, channels=channels, links=links, rechts=rechts
        )

        self.erkennung = Stimmungserkennung(
            stille_schwelle=float(einstellungen.get("silence_threshold", 0.02)),
            stille_sekunden=float(einstellungen.get("silence_seconds", 6.0)),
            sprache_sekunden=float(einstellungen.get("speech_seconds", 0.0)),
        )

        self.einstellungen = dict(einstellungen)

        self._laeuft = True

        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

        self.logger.info("Lichtshow gestartet.")

    def stop(self) -> None:
        """Die Show beenden und auf den letzten Stand warten."""

        if not self._laeuft:
            return

        self._laeuft = False

        #
        # Ein leerer Eintrag weckt den Thread, falls er gerade auf die
        # Warteschlange wartet - sonst haengt das Beenden bis zum
        # naechsten Audioblock.
        #
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass

        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

        self.logger.info("Lichtshow beendet.")

    # ----------------------------------------------------------------
    # Der Weg vom Recorder herein
    # ----------------------------------------------------------------

    def block_empfangen(self, block: bytes) -> None:
        """
        Wird IM Recorder-Thread aufgerufen. Nur ablegen, nichts
        rechnen - siehe Kopf dieser Datei.
        """

        if not self._laeuft:
            return

        try:
            self._queue.put_nowait(block)

        except queue.Full:
            self.verworfen += 1

    # ----------------------------------------------------------------
    # Der Thread
    # ----------------------------------------------------------------

    def _worker(self) -> None:

        while self._laeuft:

            try:
                block = self._queue.get(timeout=0.5)

            except queue.Empty:
                continue

            if block is None:
                continue

            try:
                self._schritt(block)

            except Exception as fehler:

                #
                # Nur melden, nicht abbrechen: Ein Rechenfehler darf
                # die Show anhalten, aber nicht den Thread verlieren -
                # sonst bliebe es dunkel, bis jemand XRack neu
                # startet.
                #
                self.logger.error("Lichtshow: Fehler beim Rechnen: %s", fehler)

    def _schritt(self, block: bytes) -> None:
        """Ein Block: analysieren, abbilden, senden."""

        self.stand = self.analyse.verarbeite(block)

        dauer = len(block) / max(1, self.analyse.channels * 4 * self.analyse.rate)

        vorher = self.zustand
        self.zustand = self.erkennung.aktualisieren(self.stand, dauer)

        #
        # Kein Takt mehr - dann uebernimmt die Rueckfallszene, und die
        # Show haelt sich heraus, bis wieder Musik kommt.
        #
        if self.zustand != "music":

            if vorher == "music":
                self.application.licht_rueckfall(self.zustand)

            return

        if vorher != "music":
            self.logger.info("Lichtshow: wieder Musik erkannt.")

        if self.stand["beat"]:
            self.position += 1

        self.phase += 0.02 + 0.08 * self.stand["low"]

        self.application.licht_show_bild(self.werte_je_lampe())

    # ----------------------------------------------------------------
    # Abbildung: aus drei Zahlen wird ein Lichtbild
    # ----------------------------------------------------------------

    def werte_je_lampe(self) -> dict:
        """
        Fuer jede eingerichtete Lampe die Kanalwerte berechnen.
        """

        empfindlichkeit = float(self.einstellungen.get("sensitivity", 1.0))

        baender = {
            name: min(1.0, self.stand[name] * empfindlichkeit)
            for name in ("low", "mid", "high")
        }

        vorlagen = self.application.lighting_store.vorlagen()

        ergebnis = {}

        for lampe in self.application.lighting_store.lampen():

            vorlage = vorlagen.get(lampe.get("template"))

            if vorlage is None:
                continue

            ergebnis[lampe["id"]] = self._werte(vorlage, baender)

        return ergebnis

    def _werte(self, vorlage: dict, baender: dict) -> list[int]:
        """Die Kanalwerte einer einzelnen Lampe."""

        kanaele = vorlage["channels"]
        werte = [0] * len(kanaele)

        gruppen = self._gruppen(kanaele)

        for nummer, gruppe in enumerate(gruppen):

            #
            # Der wandernde Punkt: das Segment, das gerade "dran" ist,
            # leuchtet voll, die anderen mit Grundhelligkeit. Bei
            # einer einzelnen Gruppe faellt das weg.
            #
            if len(gruppen) > 1:
                dran = (self.position % len(gruppen)) == nummer
                staerke = 1.0 if dran else self.GRUNDHELLIGKEIT
            else:
                staerke = 1.0

            for band, rolle in BAND_ZU_FARBE:

                for index in gruppe:

                    if kanaele[index] == rolle:
                        werte[index] = fixtures.begrenzen(
                            baender[band] * staerke * 255
                        )

            #
            # Weiss/Amber/UV bekommen den Mittelwert - sonst blieben
            # sie bei einem RGBW-Geraet dauerhaft dunkel.
            #
            for index in gruppe:

                if kanaele[index] in ("white", "amber", "uv"):
                    werte[index] = fixtures.begrenzen(
                        baender["mid"] * staerke * 180
                    )

        #
        # Bewegung: ein langsamer Schwenk, dessen Tempo am Bass haengt.
        # Bewusst zurueckhaltend - eine Choreografie, die aussieht wie
        # von Hand gebaut, ist mit drei Zahlen nicht zu haben, und ein
        # hektisch zuckender Scheinwerfer ist schlimmer als ein
        # ruhiger.
        #
        for index, rolle in enumerate(kanaele):

            if rolle == "pan":
                werte[index] = fixtures.begrenzen(
                    127 + 100 * math.sin(self.phase)
                )

            elif rolle == "tilt":
                werte[index] = fixtures.begrenzen(
                    127 + 60 * math.sin(self.phase * 0.5)
                )

            #
            # Strobe und Shutter bleiben, wo sie sind: Ein Blitzlicht,
            # das von selbst angeht, ist auf einer Buehne keine
            # Ueberraschung, die jemand haben will.
            #

        return werte

    @staticmethod
    def _gruppen(rollen: list[str]) -> list[list[int]]:
        """
        Kanäle zu Segmenten zusammenfassen - dieselbe Regel wie in der
        Oberfläche: Sobald sich eine Rolle innerhalb der laufenden
        Gruppe wiederholt, fängt eine neue an.

        Aus [rot,grün,blau] x 8 werden so acht Segmente.
        """

        gruppen = []
        laufend: list[int] = []
        gesehen: set[str] = set()

        for index, rolle in enumerate(rollen):

            if rolle in gesehen:
                gruppen.append(laufend)
                laufend = []
                gesehen = set()

            laufend.append(index)
            gesehen.add(rolle)

        if laufend:
            gruppen.append(laufend)

        return gruppen
