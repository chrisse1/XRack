"""
Audioanalyse für die musikgesteuerte Lichtshow.

Aus einem Stereo-Kanalpaar werden drei Werte gewonnen - tief, mittel,
hoch, je zwischen 0 und 1 - plus die Erkennung von Schlägen und von
Stille.

Warum Filter und keine Frequenzanalyse (FFT):

Für Licht braucht es keine Frequenzauflösung, sondern drei
Hüllkurven. Die bekommt man mit zwei Tiefpassfiltern erster Ordnung
und ein paar Rechenschritten pro Abtastwert - ohne numpy, ohne
zusätzliches Paket, und mit einem Bruchteil des Aufwands. Der Pi
nimmt nebenbei mehrkanalig auf; was hier gespart wird, fehlt dort
nicht.

Der Aufbau:

    tief   = Tiefpass bei ~200 Hz          (Bass, Kick)
    mittel = Tiefpass bei ~2 kHz minus tief (Stimme, Snare)
    hoch   = alles minus Tiefpass bei 2 kHz (Becken, Hi-Hats)

Danach gleichrichten und glätten - schnell anziehen, langsam
abfallen, so wie ein Pegelmesser. Das ergibt Werte, die sich zum
Ansteuern von Licht eignen, ohne bei jedem Abtastwert zu zappeln.

Was hier NICHT passiert: Takterkennung im musikalischen Sinn. Was als
"Schlag" gemeldet wird, ist ein plötzlicher Anstieg im Bassbereich
gegenüber dem, was gerade üblich war. Das reicht für Licht, das im
Takt blitzt, und es ist ehrlicher als ein Versprechen, das ein
einfaches Verfahren nicht halten kann.
"""

import array
import math

#
# Grenzfrequenzen der beiden Tiefpässe.
#
TIEF_HZ = 200.0
MITTE_HZ = 2000.0

#
# Wie schnell die Hüllkurve anzieht und wieder abfällt, in Sekunden.
# Schnell hoch, langsam runter - sonst flackert das Licht bei jedem
# kurzen Einbruch im Signal.
#
ANSTIEG_S = 0.010
ABFALL_S = 0.250

#
# S32_LE: ALSA liefert 24 Bit linksbündig in 32 Bit (siehe
# audio/audio_backend.py). Der größte Betrag ist deshalb 2^31.
#
VOLLAUSSCHLAG = 2.0 ** 31

#
# Untergrenze der mitlaufenden Spitzenwerte. Verhindert, dass in der
# Stille durch Teilen durch fast Null aus Rauschen eine Lichtshow
# wird.
#
SPITZE_MIN = 0.005

#
# Wie schnell die Spitzenwerte absinken (Anteil je Block).
#
SPITZE_ABFALL = 0.02


def _koeffizient(sekunden: float, rate: int) -> float:
    """
    Koeffizient eines Tiefpasses erster Ordnung aus einer Zeitkonstante.

    Ein Wert nahe 1 heißt träge, nahe 0 heißt flink.
    """

    if sekunden <= 0 or rate <= 0:
        return 0.0

    return math.exp(-1.0 / (sekunden * rate))


class Bandanalyse:
    """
    Rechnet Blöcke roher PCM-Daten in drei Hüllkurven um.

    Der Zustand (Filter, Hüllkurven, gleitender Mittelwert) bleibt
    zwischen den Blöcken erhalten - deshalb eine Klasse und keine
    Funktion. Ein Block ist rund 20 Millisekunden lang; ohne
    fortgeführten Zustand gäbe es an jeder Blockgrenze einen Sprung.
    """

    SPITZE_MIN = SPITZE_MIN

    def __init__(self, rate: int = 48000, channels: int = 2,
                 links: int = 0, rechts: int = 1):

        self.rate = max(1, int(rate))
        self.channels = max(1, int(channels))
        self.links = links
        self.rechts = rechts

        #
        # Tiefpässe: pro Abtastwert ein Schritt Richtung Eingang.
        # 2*pi*f/rate ist die uebliche Naeherung fuer die
        # Schrittweite eines Tiefpasses erster Ordnung.
        #
        self.a_tief = min(1.0, 2.0 * math.pi * TIEF_HZ / self.rate)
        self.a_mitte = min(1.0, 2.0 * math.pi * MITTE_HZ / self.rate)

        self.anstieg = _koeffizient(ANSTIEG_S, self.rate)
        self.abfall = _koeffizient(ABFALL_S, self.rate)

        self._tief = 0.0
        self._mitte = 0.0

        self.tief = 0.0
        self.mittel = 0.0
        self.hoch = 0.0

        #
        # Mitlaufende Spitzenwerte je Band.
        #
        # Ohne die haette man eine feste Verstaerkung - und die ist
        # immer falsch: Was vom Pult kommt, schwankt je nach Aufbau um
        # Groessenordnungen. Bei zu kleiner Verstaerkung bleibt das
        # Licht dunkel, bei zu grosser steht alles auf Anschlag und
        # die Baender sind nicht mehr auseinanderzuhalten (genau das
        # war beim ersten Anlauf zu sehen: 60 Hz ergab in allen drei
        # Baendern fast 1,0).
        #
        # Die Spitze sinkt langsam ab, damit die Show nach einem
        # lauten Stueck nicht minutenlang zu dunkel bleibt.
        #
        # EINE gemeinsame Spitze fuer alle drei Baender, nicht je
        # eine: Mit getrennten Spitzen wird jedes Band gegen sich
        # selbst gemessen, und ein reiner Basston stuende dann in
        # allen dreien auf 1,0 - die Verhaeltnisse zwischen den
        # Baendern waeren weg, und genau die sind das Interessante.
        # (Auch das war beim Ausprobieren zu sehen, bevor es hier
        # stand.)
        #
        self.spitze = self.SPITZE_MIN

        #
        # Gleitender Mittelwert des Bassbandes - die Bezugsgröße für
        # die Schlagerkennung. Wer feste Schwellen benutzt, bekommt
        # bei leiser Musik keine Schläge und bei lauter dauernd
        # welche.
        #
        self.bass_mittel = 0.0

        #
        # Sperrzeit nach einem Schlag, damit ein einzelner Kick nicht
        # dreimal gemeldet wird.
        #
        self.sperre_bis = 0.0
        self.zeit = 0.0

    # ----------------------------------------------------------------

    def _mono(self, block: bytes) -> array.array:
        """
        Das gewählte Kanalpaar zu Mono zusammenfassen.

        Der Block enthält alle Kanäle des Interfaces verschachtelt;
        herausgeschnitten wird nur, was die Show hören soll.
        """

        werte = array.array("i")
        werte.frombytes(block[:len(block) - (len(block) % 4)])

        mono = array.array("d")

        schritt = self.channels

        links = self.links
        rechts = self.rechts

        if schritt <= 0:
            return mono

        for rahmen in range(0, len(werte) - schritt + 1, schritt):

            l = werte[rahmen + links] if links < schritt else 0
            r = werte[rahmen + rechts] if rechts < schritt else l

            mono.append((l + r) * 0.5 / VOLLAUSSCHLAG)

        return mono

    def verarbeite(self, block: bytes) -> dict:
        """
        Einen Block verrechnen und den aktuellen Stand liefern.

        Zurück kommen die drei Hüllkurven (0-1), der Gesamtpegel, ob
        gerade ein Schlag war und wie lange schon nichts mehr kam.
        """

        mono = self._mono(block)

        if not mono:
            return self.stand(False)

        summe = 0.0
        schlag = False

        for wert in mono:

            #
            # Zwei Tiefpässe, daraus drei Bänder.
            #
            self._tief += self.a_tief * (wert - self._tief)
            self._mitte += self.a_mitte * (wert - self._mitte)

            tief = abs(self._tief)
            mittel = abs(self._mitte - self._tief)
            hoch = abs(wert - self._mitte)

            self.tief = self._huellkurve(self.tief, tief)
            self.mittel = self._huellkurve(self.mittel, mittel)
            self.hoch = self._huellkurve(self.hoch, hoch)

            summe += wert * wert

        #
        # Der Bass gegen seinen eigenen gleitenden Mittelwert: Ein
        # Schlag ist ein deutlicher Ausreißer nach oben, nicht ein
        # absoluter Wert.
        #
        dauer = len(mono) / self.rate
        self.zeit += dauer

        if self.tief > self.bass_mittel * 1.5 and self.zeit >= self.sperre_bis:

            schlag = True
            self.sperre_bis = self.zeit + 0.12

        #
        # Der Mittelwert zieht langsam nach, damit er einem
        # Lautstaerkewechsel folgt, aber nicht dem einzelnen Schlag.
        #
        self.bass_mittel += 0.05 * (self.tief - self.bass_mittel)

        self.pegel = math.sqrt(summe / len(mono))

        self.spitzen_nachfuehren()

        return self.stand(schlag)

    def _huellkurve(self, bisher: float, jetzt: float) -> float:
        """Schnell anziehen, langsam abfallen."""

        faktor = self.anstieg if jetzt > bisher else self.abfall

        return jetzt + faktor * (bisher - jetzt)

    def _normiert(self, wert: float, spitze: float) -> float:
        """Auf 0-1 bezogen auf den mitlaufenden Spitzenwert."""

        if spitze <= 0:
            return 0.0

        return max(0.0, min(1.0, wert / spitze))

    def spitzen_nachfuehren(self) -> None:
        """
        Die gemeinsame Spitze anheben, wenn es lauter wurde, sonst
        langsam absenken.
        """

        self.spitze = max(
            self.tief,
            self.mittel,
            self.hoch,
            self.spitze * (1.0 - SPITZE_ABFALL),
            SPITZE_MIN,
        )

    def stand(self, schlag: bool = False) -> dict:
        """Der aktuelle Stand als einfache Werte."""

        return {
            "low": self._normiert(self.tief, self.spitze),
            "mid": self._normiert(self.mittel, self.spitze),
            "high": self._normiert(self.hoch, self.spitze),
            #
            # Der Pegel bleibt absolut: Er entscheidet ueber "Stille",
            # und eine mitlaufende Normierung wuerde aus Rauschen
            # wieder Vollausschlag machen.
            #
            "level": min(1.0, getattr(self, "pegel", 0.0)),
            "beat": schlag,
        }


class Stimmungserkennung:
    """
    Entscheidet, ob gerade Musik läuft, nur gesprochen wird oder
    nichts kommt.

    Das ist die unsicherste Stelle der ganzen Lichtsteuerung, und das
    soll auch so dastehen: Ob ein leiser Teil eines Stücks noch Musik
    ist oder schon eine Ansage, lässt sich aus drei Hüllkurven nicht
    zuverlässig entscheiden. Deshalb zwei Vorkehrungen:

      - Der eindeutige Fall zuerst. Anhaltende Stille ist sicher
        erkennbar und deckt den häufigsten Anlass ab (Pause, niemand
        spielt).

      - Alles ist entprellt und einstellbar. Umgeschaltet wird erst,
        wenn ein Zustand mehrere Sekunden anhält, und die Schwellen
        liegen als Regler in der Oberfläche. Vor Ort nachjustieren
        muss ohne Codeänderung gehen.
    """

    def __init__(self, stille_schwelle: float = 0.02,
                 stille_sekunden: float = 6.0,
                 sprache_sekunden: float = 12.0):

        self.stille_schwelle = stille_schwelle
        self.stille_sekunden = stille_sekunden
        self.sprache_sekunden = sprache_sekunden

        self.leise_seit = 0.0
        self.ohne_schlag_seit = 0.0

        #
        # "music", "speech" oder "silence".
        #
        self.zustand = "music"

    def aktualisieren(self, werte: dict, dauer: float) -> str:
        """
        Einen Analyseschritt einarbeiten und den Zustand liefern.

        `dauer` ist die Länge des verarbeiteten Blocks in Sekunden.
        """

        if werte["level"] < self.stille_schwelle:
            self.leise_seit += dauer
        else:
            self.leise_seit = 0.0

        if werte["beat"]:
            self.ohne_schlag_seit = 0.0
        else:
            self.ohne_schlag_seit += dauer

        #
        # Stille schlaegt alles: eindeutig und ohne Auslegung.
        #
        if self.leise_seit >= self.stille_sekunden:
            self.zustand = "silence"

        elif self.ohne_schlag_seit >= self.sprache_sekunden:
            #
            # Kein Bass-Puls ueber lange Zeit, aber es kommt etwas:
            # sehr wahrscheinlich eine Ansage. Die Entprellzeit ist
            # bewusst lang - eine ruhige Strophe soll nicht reichen.
            #
            self.zustand = "speech"

        else:
            self.zustand = "music"

        return self.zustand
