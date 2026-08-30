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
import time

from lighting import fixtures
from lighting.analysis import (
    SNARE_SCHWELLE,
    Bandanalyse,
    Stimmungserkennung,
)

#
# Die drei Bänder und die Einstellung, in der ihre Farbe steht.
#
# Früher war die Zuordnung fest verdrahtet (tief rot, mittel grün,
# hoch blau). Das ist eine brauchbare Vorgabe, aber Geschmack und
# nicht Physik - deshalb kommt die Farbe jetzt aus den Einstellungen,
# und jedes Band kann jede Farbe bekommen.
#
BAENDER = (
    ("low", "color_low"),
    ("mid", "color_mid"),
    ("high", "color_high"),
)

#
# Vorgabefarben, falls in den Einstellungen keine stehen.
#
# Ohne die wird aus einer fehlenden Einstellung Schwarz, und die
# ganze Show bleibt dunkel - ein fehlender Wert darf nicht "kein
# Licht" bedeuten. Betrifft alte gespeicherte Einrichtungen, die die
# Farben noch nicht kennen.
#
VORGABE_FARBEN = {
    "color_low": "#ff0000",
    "color_mid": "#00ff00",
    "color_high": "#0000ff",

    # Der Satz der ersten Hintergrundgruppe.
    "color_low_1": "#ff0000",
    "color_mid_1": "#00ff00",
    "color_high_1": "#0000ff",

    # Und der der zweiten.
    "color_low_2": "#ff00ff",
    "color_mid_2": "#ffaa00",
    "color_high_2": "#00ffff",
}

#
# Welchen Farbsatz eine Lampenart benutzt.
#
# Jede Art hat ihren eigenen Satz. Das ist die einzige Stelle, an der
# die Zuordnung steht.
#
# Anfangs teilten sich Effektlicht und Hintergrund 1 den namenlosen
# Satz. Das war nirgends aufgeschrieben und fiel erst auf, als die
# Ueberschrift im Dialog "Farben der Frequenzbereiche" hiess und
# stillschweigend fuer zwei Dinge galt.
#
FARBSATZ = {
    "effect": "",
    "background": "_1",
    "background2": "_2",
}

#
# Die Farbkanäle einer Lampe in der Reihenfolge Rot/Grün/Blau.
#
RGB_ROLLEN = ("red", "green", "blue")


def farbe_zerlegen(text: str) -> tuple[int, int, int]:
    """
    "#rrggbb" in drei Zahlen. Bei Unsinn Schwarz - eine kaputte
    Farbe soll die Show nicht anhalten.
    """

    text = str(text or "").strip().lstrip("#")

    if len(text) != 6:
        return (0, 0, 0)

    try:
        return (
            int(text[0:2], 16),
            int(text[2:4], 16),
            int(text[4:6], 16),
        )

    except ValueError:
        return (0, 0, 0)


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

    #
    # Wie schnell der Puls nach einem Schlag wieder abfaellt.
    #
    # Derselbe Wert wie die Release-Zeit der Huellkurven in
    # analysis.py (ABFALL_S) und aus demselben Grund: Bei 120 BPM
    # liegt eine halbe Sekunde zwischen zwei Schlaegen, der Puls ist
    # bis dahin also weitgehend unten - und trotzdem traege genug,
    # dass es zwischendurch nicht flackert.
    #
    PULS_ABFALL_S = 0.25

    #
    # Wie lange ein Blitz auf der Snare steht.
    #
    # 80 ms sind vier Lichtbilder - kurz genug, dass es ein Blitz
    # bleibt und kein Blinken, lang genug, dass es auch ein Geraet
    # zeigt, das den Kanal als Blitzgeschwindigkeit liest.
    #
    BLITZ_DAUER_S = 0.08

    #
    # Was ohne Einstellung waehrend des Blitzes auf dem Kanal steht
    # (Anteil von 255).
    #
    BLITZ_STAERKE = 0.8

    #
    # Drehung eines Derby-/Effektspiegels.
    #
    # Die Handbuecher der Eurolite-Geraete kodieren das gleich:
    # 0-4 steht, ab etwa 5 vorwaerts von langsam nach schnell, in
    # der oberen Haelfte rueckwaerts. Angesteuert wird nur die
    # untere, vorwaerts laufende Haelfte, und auch die nur zur
    # Haelfte - ein Derby, der auf Anschlag rotiert, ist nach zwei
    # Minuten anstrengend.
    #
    DREHUNG_MIN = 10
    DREHUNG_SPANNE = 60

    #
    # Laser.
    #
    # Laut Handbuch ist 0-4 aus, 5-9 an, ab 10 Strobe. Angesteuert
    # wird nur "an" - ein blitzender Laser ist eine ganz andere
    # Hausnummer als ein stehender, und niemand will ihn ungefragt.
    # 7 sitzt in der Mitte des An-Bereichs, also weit weg von
    # beiden Kanten.
    #
    LASER_AN = 7

    #
    # Ab dieser Bandstaerke geht ein Laser an. Die Baender sind
    # ueber 250 ms geglaettet (siehe analysis.py), deshalb flackert
    # das nicht im Takt der Bildrate.
    #
    LASER_SCHWELLE = 0.25

    #
    # Wie traege das Hintergrundlicht folgt, falls in den
    # Einstellungen nichts steht.
    #
    HINTERGRUND_VORGABE_S = 4.0

    #
    # Nach wie vielen Schlaegen das Hintergrundlicht auf die naechste
    # der drei Farben wechselt, falls in den Einstellungen nichts
    # steht.
    #
    # 16 Schlaege sind bei 120 BPM rund acht Sekunden, also etwa vier
    # Takte: lang genug, dass eine Farbe wirklich steht, kurz genug,
    # dass man alle drei zu sehen bekommt.
    #
    HINTERGRUND_VORGABE_SCHLAEGE = 16

    #
    # Wie lange ein Schlag hoechstens dauern darf, bevor der Wechsel
    # stattdessen nach der Uhr geht.
    #
    # 1,5 Sekunden je Schlag entsprechen 40 BPM - langsamer ist keine
    # Musik, die jemand auflegt. Der Zeitweg greift also nur, wenn die
    # Takterkennung wirklich nichts findet; ohne ihn stuende die Farbe
    # bei einer ruhigen Passage einfach still, und das saehe aus wie
    # ein Fehler.
    #
    HINTERGRUND_ERSATZ_S = 1.5

    #
    # Wie lange ein Block dauert, wenn niemand es besser weiss.
    #
    # Gebraucht wird das nur, wenn werte_je_lampe() ohne einen
    # vorangegangenen _schritt() aufgerufen wird - im Test. Im Betrieb
    # setzt _schritt() den echten Wert.
    #
    BLOCK_VORGABE_S = 0.02

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
                            "level": 0.0, "beat": False, "snare": False}

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

        #
        # Die Pulshuellkurve (0-1) fuer den zweiten Show-Modus.
        #
        # EINE Zahl fuer alle Effektlampen, so wie hintergrund_farbe
        # eine fuer alle Hintergrundlampen ist: Ein Puls, bei dem
        # jede Lampe woanders steht, ist kein Puls mehr.
        #
        self.puls = 0.0

        #
        # Wie lange der Blitz auf der Snare noch steht, in Sekunden.
        #
        self.blitz = 0.0

        self.verworfen = 0

        #
        # Wann kam der letzte Block? Bleibt der Audiostrom weg -
        # etwa weil der Lesethread gestorben ist -, wartet dieser
        # Thread stumm weiter, und in der Karte sieht alles aus wie
        # zuvor. Genau das war am Geraet nicht zu unterscheiden von
        # "die Show tut nichts mehr".
        #
        self.letzter_block = 0.0
        self.bloecke = 0

        #
        # Je Hintergrundlampe die geglaettete Farbe als
        # [rot, gruen, blau, mitte].
        #
        # "mitte" muss mit hinein, weil Weiss/Amber/UV aus dem
        # mittleren Band kommen - sonst waere die Farbe ruhig und das
        # Weiss daneben zappelig.
        #
        self._hintergrund: dict[str, list[float]] = {}

        #
        # Welche der drei Farben das Hintergrundlicht gerade ansteuert,
        # und wie lange schon.
        #
        # Bewusst EINE Zahl fuer alle Hintergrundlampen: Ein Wash, bei
        # dem jede Lampe eine andere Farbe zeigt, ist kein Wash mehr.
        #
        self.hintergrund_farbe = 0
        self.hintergrund_schlaege = 0
        self.hintergrund_zeit = 0.0

        #
        # Die Dauer des zuletzt verarbeiteten Blocks. Die Glaettung
        # braucht sie, und nur _schritt() kennt sie.
        #
        self.letzte_dauer = self.BLOCK_VORGABE_S

    # ----------------------------------------------------------------
    # An und aus
    # ----------------------------------------------------------------

    #
    # Nach so vielen Sekunden ohne Block gilt der Strom als weg.
    # Ein Block kommt alle ~20 ms; zwei Sekunden sind also eine
    # Ewigkeit und kein Grenzfall.
    #
    STROM_WEG_S = 2.0

    @property
    def running(self) -> bool:
        return self._laeuft

    @property
    def strom_da(self) -> bool:
        """
        True, wenn in letzter Zeit noch Bloecke angekommen sind.

        Ohne diese Auskunft steht in der Karte "Show laeuft", waehrend
        in Wirklichkeit nichts mehr hereinkommt.
        """

        if not self._laeuft or self.letzter_block == 0.0:
            return False

        return (time.monotonic() - self.letzter_block) < self.STROM_WEG_S

    def start(self, rate: int, channels: int,
              links: int, rechts: int, einstellungen: dict) -> None:
        """Die Show starten."""

        if self._laeuft:
            return

        self.analyse = Bandanalyse(
            rate=rate, channels=channels, links=links, rechts=rechts,
            snare_schwelle=float(
                einstellungen.get("snare_threshold") or SNARE_SCHWELLE
            ),
        )

        self.erkennung = Stimmungserkennung(
            stille_schwelle=float(einstellungen.get("silence_threshold", 0.02)),
            stille_sekunden=float(einstellungen.get("silence_seconds", 6.0)),
            sprache_sekunden=float(einstellungen.get("speech_seconds", 0.0)),
        )

        self.einstellungen = dict(einstellungen)

        self.letzter_block = 0.0
        self.bloecke = 0
        self.verworfen = 0

        #
        # Ohne das haengt die Farbe der letzten Show nach: Man
        # startet neu und das Hintergrundlicht braucht Sekunden, um
        # von einer Farbe wegzukommen, die zu ganz anderer Musik
        # gehoerte.
        #
        self._hintergrund.clear()
        self.hintergrund_farbe = 0
        self.hintergrund_schlaege = 0
        self.hintergrund_zeit = 0.0
        self.puls = 0.0
        self.blitz = 0.0
        self.letzte_dauer = self.BLOCK_VORGABE_S

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

        self.letzter_block = time.monotonic()
        self.bloecke += 1

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

        self.letzte_dauer = dauer or self.BLOCK_VORGABE_S

        vorher = self.zustand
        self.zustand = self.erkennung.aktualisieren(self.stand, dauer)

        #
        # Kein Takt mehr - dann uebernimmt die Rueckfallszene, und die
        # Show haelt sich heraus, bis wieder Musik kommt.
        #
        if self.zustand != "music":

            if vorher == "music":
                self.application.licht_rueckfall(self.zustand)

            #
            # Und bei JEDEM weiteren Block die Blende weiterziehen.
            #
            # Nur beim Uebergang zu rufen hiesse: einmal springen -
            # und genau das soll ja weg. Ist die Blende durch, kostet
            # der Aufruf nichts, er kehrt sofort zurueck.
            #
            self.application.licht_rueckfall_halten(dauer)

            return

        if vorher != "music":
            self.logger.info("Lichtshow: wieder Musik erkannt.")

        if self.stand["beat"]:
            self.position += 1

        self._farbe_weiterschalten(dauer, bool(self.stand["beat"]))
        self._puls_weiterschalten(dauer, bool(self.stand["beat"]))
        self._blitz_weiterschalten(dauer, bool(self.stand.get("snare")))

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

        #
        # Einmal je Bild zerlegen, nicht je Lampe und Segment.
        #
        farben = {
            band + anhang: farbe_zerlegen(
                self.einstellungen.get(einstellung + anhang)
                or VORGABE_FARBEN[einstellung + anhang]
            )
            for band, einstellung in BAENDER
            for anhang in ("", "_1", "_2")
        }

        vorlagen = self.application.lighting_store.vorlagen()

        ergebnis = {}

        for lampe in self.application.lighting_store.lampen():

            vorlage = vorlagen.get(lampe.get("template"))

            if vorlage is None:
                continue

            vorher = self.application.light_values.get(lampe["id"])

            art = lampe.get("kind", fixtures.ART_VORGABE)

            #
            # Eine ausgenommene Lampe bekommt zurueck, was schon an
            # ihr steht - sie einfach WEGZULASSEN waere ein Fehler:
            # licht_show_bild() ersetzt das Bild vollstaendig, die
            # Lampe fehlte darin, und fixtures.bild() liest fehlende
            # Werte als Nullen. Sie ginge also aus, statt stehen zu
            # bleiben.
            #
            if art == "static":

                anzahl = len(vorlage["channels"])

                werte = list(vorher or [])[:anzahl]
                werte += [0] * (anzahl - len(werte))

                ergebnis[lampe["id"]] = werte
                continue

            ergebnis[lampe["id"]] = self._werte(
                vorlage, baender, farben, vorher,
                art=art, kennung=lampe["id"],
            )

        return ergebnis

    def _farbe_weiterschalten(self, dauer: float, schlag: bool) -> None:
        """
        Das Hintergrundlicht auf die naechste der drei Farben
        weiterschalten, wenn es soweit ist.

        Gezaehlt werden Schlaege, nicht Sekunden - damit haengt der
        Wechsel am Tempo der Musik, ohne dass XRack dafuer BPM in
        Zahlen schaetzen muesste. Der vorhandene Taktzaehler reicht
        dafuer aus; er treibt schon das Lauflicht.

        Der Zeitweg daneben ist ein Notnagel: Findet die Erkennung
        keinen Takt, stuende die Farbe sonst still, und das sieht aus
        wie ein Fehler.
        """

        schlaege = max(1, int(
            self.einstellungen.get("background_beats")
            or self.HINTERGRUND_VORGABE_SCHLAEGE
        ))

        if schlag:
            self.hintergrund_schlaege += 1

        self.hintergrund_zeit += dauer

        if (self.hintergrund_schlaege >= schlaege
                or self.hintergrund_zeit >= schlaege * self.HINTERGRUND_ERSATZ_S):

            self.hintergrund_farbe = (self.hintergrund_farbe + 1) % len(BAENDER)
            self.hintergrund_schlaege = 0
            self.hintergrund_zeit = 0.0

    def _puls_weiterschalten(self, dauer: float, schlag: bool) -> None:
        """
        Die Pulshuellkurve fuehren: bei einem Schlag auf voll, sonst
        abfallen.

        Dieselbe Ein-Pol-Rechnung wie ueberall sonst im Programm
        (analysis.py, _geglaettet), nur mit einer eigenen
        Zeitkonstante und einer einzelnen Zahl statt einer Farbe.

        Bewusst hart auf 1.0 statt weich hoch: Ein Puls, der erst
        anschwillt, kommt hinter dem Schlag her - und dann sieht das
        Licht aus, als haenge es der Musik hinterher.
        """

        if schlag:
            self.puls = 1.0
            return

        nachleuchten = max(0.02, float(
            self.einstellungen.get("pulse_seconds") or self.PULS_ABFALL_S
        ))

        anteil = min(1.0, dauer / nachleuchten)

        self.puls += anteil * (0.0 - self.puls)

    def _blitz_weiterschalten(self, dauer: float, snare: bool) -> None:
        """
        Den Blitz auf der Snare fuehren: bei einem Schlag anwerfen,
        sonst ablaufen lassen.

        Kein weicher Abfall wie beim Puls - ein Blitz ist an oder aus.
        Kommt waehrenddessen der naechste Schlag, faengt die Zeit von
        vorne an.
        """

        if snare:
            self.blitz = self.BLITZ_DAUER_S
            return

        self.blitz = max(0.0, self.blitz - dauer)

    def _geglaettet(self, kennung: str, ziel: list[float]) -> list[float]:
        """
        Einen Wert je Lampe langsam an sein Ziel heranfuehren.

        Dieselbe Rechnung wie beim Bass-Mittelwert in analysis.py -
        ein Tiefpass erster Ordnung, dessen Zeitkonstante in Sekunden
        angegeben ist. Ein zweites Glaettungsverfahren im Programm
        waere eines zu viel.
        """

        traegheit = max(0.1, float(
            self.einstellungen.get("background_seconds")
            or self.HINTERGRUND_VORGABE_S
        ))

        stand = self._hintergrund.get(kennung)

        #
        # Beim ersten Bild direkt auf den Zielwert, statt aus dem
        # Dunkeln hochzufahren: Sonst braeuchte jede Hintergrundlampe
        # nach dem Start der Show erst mal Sekunden, bis ueberhaupt
        # etwas zu sehen ist.
        #
        if stand is None or len(stand) != len(ziel):
            stand = list(ziel)

        else:
            anteil = min(1.0, self.letzte_dauer / traegheit)

            stand = [
                wert + anteil * (z - wert)
                for wert, z in zip(stand, ziel)
            ]

        self._hintergrund[kennung] = stand

        return stand

    def _werte(self, vorlage: dict, baender: dict, farben: dict,
               vorher: list[int] | None = None,
               art: str = "effect", kennung: str = "") -> list[int]:
        """Die Kanalwerte einer einzelnen Lampe."""

        hintergrund = art in fixtures.HINTERGRUND_ARTEN

        #
        # Der zweite Show-Modus: Statt des wandernden Punktes atmen
        # alle Segmente gemeinsam im Takt.
        #
        # Nur fuer Effektlicht. Das Hintergrundlicht hat sein eigenes
        # Bild - eine Farbe, weich uebergeblendet -, und ein Wash,
        # der im Takt zuckt, ist kein Wash mehr.
        #
        pulsieren = (
            not hintergrund
            and self.einstellungen.get("effect_mode") == "pulse"
        )

        #
        # Wie hell es zwischen zwei Schlaegen bleibt.
        #
        # Hier steht bewusst kein "or": 0 ist an dieser Stelle ein
        # gueltiger Wert ("dazwischen ganz aus") und wuerde von "or"
        # still in die Vorgabe verwandelt. Der Regler haette am
        # linken Anschlag einfach keine Wirkung, und niemand saehe,
        # warum.
        #
        boden = self.einstellungen.get("pulse_base")

        boden = (
            self.GRUNDHELLIGKEIT if boden is None
            else max(0.0, min(1.0, float(boden)))
        )

        #
        # Blitzt diese Lampe auf die Snare?
        #
        # Beim Hintergrundlicht nicht: Ein Wash, in den ein Blitz
        # hineinfaehrt, ist kein Wash mehr - aus demselben Grund, aus
        # dem dort auch der Puls und die Drehung ausbleiben.
        #
        blitzen = (
            not hintergrund
            and bool(self.einstellungen.get("snare_strobe"))
        )

        #
        # Was waehrend des Blitzes auf dem Kanal steht. Auch hier kein
        # "or": 0 ist ein gueltiger Wert, und er hiesse "gar kein
        # Blitz" - das darf nicht still zur Vorgabe werden.
        #
        wucht = self.einstellungen.get("snare_power")

        blitzwert = fixtures.begrenzen(255 * (
            self.BLITZ_STAERKE if wucht is None
            else max(0.0, min(1.0, float(wucht)))
        ))

        #
        # Welcher Farbsatz gilt: der erste oder der der zweiten
        # Hintergrundgruppe.
        #
        satz = FARBSATZ.get(art, "")

        kanaele = vorlage["channels"]

        #
        # Ausgangspunkt ist, was gerade an der Lampe steht - nicht
        # Null.
        #
        # Die Show faehrt nur Farbe und Bewegung. Strobe, Shutter,
        # Drehung, Laser, Gobo und die Sonstigen laesst sie mit
        # Absicht in Ruhe. "In Ruhe lassen" hiess aber bisher, sie
        # bei jedem Bild auf 0 zu schreiben - und da alle 20 ms ein
        # Bild kommt, war jeder von Hand gestellte Regler eine
        # Zwanzigstelsekunde spaeter wieder aus. Von aussen sah das
        # aus, als taeten diese Regler gar nichts.
        #
        werte = [fixtures.begrenzen(wert) for wert in (vorher or [])[:len(kanaele)]]
        werte += [0] * (len(kanaele) - len(werte))

        gruppen = self._gruppen(kanaele)

        #
        # Nur Gruppen mit Farbkanaelen kommen fuer das Lauflicht in
        # Frage - was leuchten kann, steht in fixtures.FARBROLLEN.
        #
        # Bei einer schlichten LED-Bar sind das alle, und es aendert
        # sich nichts. An den grossen Sets aber landen Kanaele wie
        # "interne Programme", Laser oder Strobe-LEDs in eigenen
        # Gruppen ohne jede Farbe. Zaehlte man die mit, stuende der
        # Punkt bei der Laser-Bar in fuenf von neun Takten auf einer
        # Gruppe, die gar nicht leuchten kann - das Licht wuerde
        # scheinbar grundlos aussetzen.
        #
        farbig = [
            nummer
            for nummer, gruppe in enumerate(gruppen)
            if any(kanaele[index] in fixtures.FARBROLLEN for index in gruppe)
        ]

        dran_gruppe = (
            farbig[self.position % len(farbig)] if farbig else -1
        )

        for nummer, gruppe in enumerate(gruppen):

            #
            # Gruppen ohne Farbkanal haben hier nichts zu suchen. In
            # ihnen stehen Laser, Strobe oder Programmkanaele, und die
            # werden weiter unten einzeln behandelt.
            #
            if nummer not in farbig:
                continue

            if pulsieren:

                #
                # Der Puls: ALLE Segmente gehen bei jedem Schlag auf
                # voll und fallen bis zum naechsten zurueck. Jedes
                # behaelt dabei seine Bandfarbe und seinen Bandpegel -
                # man sieht also weiter, welches Band was macht, aber
                # die ganze Lampe atmet.
                #
                # Der Boden kommt aus den Einstellungen; ohne
                # Angabe ist es GRUNDHELLIGKEIT, also derselbe Wert
                # wie beim wandernden Punkt. Dort heisst er "wie hell
                # ist ein Segment, das gerade nicht dran ist", hier
                # "wie hell zwischen zwei Schlaegen" - dieselbe
                # Frage. Wer ihn auf 0 stellt, bekommt statt des
                # Atmens ein Blitzen; das ist seine Sache.
                #
                # Das gilt auch fuer Lampen mit nur EINER farbigen
                # Gruppe. Der wandernde Punkt laesst die aus - er
                # braucht mehrere Segmente, ueber die er wandern kann
                # -, ein einzelner RGB-Strahler tat in der Show
                # deshalb bisher nicht viel. Der Puls wirkt auf ihm
                # genauso wie auf einer achtsegmentigen Bar.
                #
                staerke = boden + (1.0 - boden) * self.puls

            #
            # Der wandernde Punkt: das Segment, das gerade "dran" ist,
            # leuchtet voll, die anderen mit Grundhelligkeit. Bei
            # einer einzelnen leuchtenden Gruppe faellt das weg.
            #
            elif len(farbig) > 1 and not hintergrund:
                staerke = 1.0 if nummer == dran_gruppe else self.GRUNDHELLIGKEIT
            else:

                #
                # Beim Hintergrundlicht leuchten alle Segmente gleich.
                # Der wandernde Punkt ist genau das, was zuckelt - und
                # ein Wash soll nicht zuckeln.
                #
                staerke = 1.0

            #
            # Die drei Bänder werden zu EINER Farbe gemischt, statt
            # jedes auf einen festen Kanal zu legen. Nur so kann ein
            # Band eine beliebige Farbe haben: "tief = orange" braucht
            # Rot UND Grün, und das ginge mit einer starren Zuordnung
            # Band->Kanal nicht.
            #
            if hintergrund:

                #
                # Das Hintergrundlicht zeigt EINE der drei Farben, nicht
                # ihre Summe.
                #
                # Das ist der Unterschied, auf den es ankommt. Addiert
                # man alle drei - so lief es zuerst -, dann steht bei
                # halbwegs ausgewogener Musik dauerhaft die Summe da,
                # und mit der ueblichen Vorgabe Rot plus Gruen plus
                # Blau ist das schlicht Weiss. Es wechselte also gar
                # nichts. Jetzt ist immer genau eine Farbe das Ziel,
                # und der Tiefpass darunter blendet weich hinueber,
                # wenn weitergeschaltet wird.
                #
                #
                # Die zweite Gruppe laeuft um eine Farbe VERSETZT.
                #
                # Ohne den Versatz zeigten beide Gruppen dieselbe
                # Stelle ihres Verlaufs, und wer zweimal dieselbe
                # Palette einstellt, saehe zwei gleiche Farben - also
                # genau nicht das, wofuer es die zweite Gruppe gibt.
                # Ein gemeinsamer Zaehler mit Versatz statt eines
                # zweiten Zaehlers: So koennen die beiden gar nicht
                # auseinanderlaufen.
                #
                versatz = 1 if art == "background2" else 0

                stelle = (self.hintergrund_farbe + versatz) % len(BAENDER)

                band = BAENDER[stelle][0]

                rot, gruen, blau = farben[band + satz]

                #
                # Die Helligkeit kommt aus dem lautesten Band, nicht
                # aus dem gerade gezeigten: Sonst wuerde der Wash
                # dunkel, sobald die Farbe eines Bandes an der Reihe
                # ist, das in diesem Stueck kaum vorkommt.
                #
                laut = max(baender.values())

                # Der Schluessel enthaelt die Gruppe, nicht nur die
                # Lampe. Das ist kein Beiwerk: Jeder Schluessel darf
                # je Bild genau einmal weiterlaufen. Bei einer Lampe
                # mit acht Segmenten waere die Glaettung sonst
                # achtmal so schnell - und damit gar keine mehr.
                gemischt = self._geglaettet(
                    f"{kennung}:{nummer}",
                    [rot * laut, gruen * laut, blau * laut],
                )

            elif len(farbig) > 1:

                #
                # Effektlicht mit mehreren Segmenten: Jedes bekommt
                # SEIN EIGENES Frequenzband, nicht die Mischung aller
                # drei.
                #
                # Vorher bekam jedes Segment dieselbe gemischte Farbe.
                # Bei Musik, in der Bass, Mitten und Hoehen alle
                # vorkommen - also bei so ziemlich jeder -, ist diese
                # Mischung mit den ueblichen Farben Rot plus Gruen
                # plus Blau schlicht Weiss. Am Geraet sah man deshalb
                # sechs weisse Spots, die nur unterschiedlich hell
                # waren. Von einer Lichtorgel war nichts zu erkennen.
                #
                # Gezaehlt wird ueber die FARBIGEN Gruppen, nicht ueber
                # alle: An der Laser Bar liegen zwischen den Spots
                # Gruppen aus Laser- und Strobekanaelen. Zaehlte man
                # die mit, saehe die Verteilung der Baender
                # willkuerlich aus.
                #
                stelle = farbig.index(nummer) % len(BAENDER)

                band = BAENDER[stelle][0]

                rot, gruen, blau = farben[band + satz]

                gemischt = [
                    rot * baender[band],
                    gruen * baender[band],
                    blau * baender[band],
                ]

            else:

                #
                # Eine einzelne Lampe ohne Segmente kann die Baender
                # nicht nebeneinander zeigen - fuer sie bleibt es bei
                # der Mischung. Ihr ein einzelnes Band zu geben hiesse,
                # dass ein RGB-Strahler allein nur noch auf den Bass
                # reagiert und die halbe Musik ignoriert.
                #
                gemischt = [0.0, 0.0, 0.0]

                for band, einstellung in BAENDER:

                    rot, gruen, blau = farben[band + satz]

                    gemischt[0] += baender[band] * rot
                    gemischt[1] += baender[band] * gruen
                    gemischt[2] += baender[band] * blau

            for stelle, rolle in enumerate(RGB_ROLLEN):

                for index in gruppe:

                    if kanaele[index] == rolle:
                        werte[index] = fixtures.begrenzen(
                            gemischt[stelle] * staerke
                        )

            #
            # Weiss, Amber und UV faehrt die Show NICHT mehr.
            #
            # Sie liefen frueher mit dem mittleren Band mit. Genau das
            # war die zweite Haelfte des Weiss-Problems: Auf einem
            # RGBW-Spot lag damit dauerhaft Weiss ueber der Farbe und
            # wusch sie aus - der Spot zeigte kein Rot, sondern ein
            # helles Rosa.
            #
            # Sie werden jetzt behandelt wie Strobe und Shutter: Die
            # Show laesst sie stehen, und wer einen Weissanteil haben
            # will, stellt ihn in der Lichtkarte von Hand ein. Er
            # bleibt dann auch waehrend der Show stehen.
            #

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

            elif rolle == "rotation" and not hintergrund:

                #
                # Der Spiegel dreht sich mit dem Bass. Immer ein
                # wenig, auch in leisen Passagen - ein Derby, der
                # zwischendurch stehenbleibt, sieht kaputt aus.
                #
                # Beim Hintergrundlicht bleibt die Drehung aus. Ein
                # rotierender Derby als Grundlicht waere ein
                # Widerspruch in sich.
                #
                werte[index] = fixtures.begrenzen(
                    self.DREHUNG_MIN + self.DREHUNG_SPANNE * baender["low"]
                )

            elif rolle == "strobe" and blitzen:

                #
                # Der Blitz auf der Snare - nur, wenn er in den
                # Einstellungen ausdruecklich eingeschaltet ist.
                #
                # Solange er aus ist, faehrt die Show die
                # Strobe-Kanaele wie bisher gar nicht: Ein Blitzlicht,
                # das von selbst angeht, ist auf einer Buehne keine
                # Ueberraschung, die jemand haben will.
                #
                # Ist er an, gehoert der Kanal aber der Show, und sie
                # schreibt zwischen den Blitzen ausdruecklich 0. Ihn
                # einfach stehen zu lassen ginge nicht: Das naechste
                # Bild beginnt bei dem, was zuletzt drin stand - der
                # Blitzwert bliebe also stehen, und das Strobe liefe
                # durch, bis jemand die Show anhaelt.
                #
                werte[index] = blitzwert if self.blitz > 0.0 else 0

            #
            # Shutter bleibt, wo er ist: Auf einem Bewegtlicht heisst
            # "zu" schlicht dunkel, und was dazwischen liegt, steht in
            # der Tabelle des jeweiligen Geraets.
            #
            # Gobo und Farbrad ebenso, aus demselben Grund: Was hinter
            # einem Wert steckt, steht in keiner Norm. 42 heisst an
            # einem Scheinwerfer "Sterne" und am naechsten "offen".
            # Ohne ein Geraet zum Ausprobieren waere jede Ansteuerung
            # geraten - und niemand koennte pruefen, ob sie stimmt.
            #

        #
        # Die Laser.
        #
        # Der erste Laserkanal haengt am tiefen Band, der zweite am
        # mittleren, der dritte am hohen - danach von vorn. An der
        # Laser Bar sind das der rote und der gruene, die damit
        # abwechselnd auf Bass und Stimmen ansprechen statt beide
        # dasselbe zu tun.
        #
        nummer = 0

        for index, rolle in enumerate(kanaele):

            #
            # Beim Hintergrundlicht bleiben die Laser aus - aus
            # demselben Grund wie die Drehung.
            #
            if rolle != "laser" or hintergrund:
                continue

            band = BAENDER[nummer % len(BAENDER)][0]
            nummer += 1

            werte[index] = (
                self.LASER_AN
                if baender[band] >= self.LASER_SCHWELLE
                else 0
            )

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
