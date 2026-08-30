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
# Zweite, flinkere Huellkurve nur fuer die Schlagerkennung.
#
# Die traege Huellkurve oben ist zum Ansteuern von Licht gedacht -
# sie soll nicht zappeln. Genau das macht sie fuer die
# Schlagerkennung aber unbrauchbar: Unter durchgehendem Bass faellt
# sie zwischen zwei Kicks gar nicht weit genug ab, und ein Kick ragt
# nicht mehr heraus. Am Geraet sah das so aus, dass die Show mitten
# in der Musik auf die Rueckfallszene sprang.
#
SCHLAG_ANSTIEG_S = 0.005
SCHLAG_ABFALL_S = 0.060

#
# Zeitkonstante des Vergleichswerts, gegen den ein Schlag gemessen
# wird - rund eine Sekunde, also mehrere Schlaege lang.
#
SCHLAG_MITTEL_S = 1.0

#
# Wie weit ein Schlag ueber dem Mittel liegen muss.
#
# 1.5 war zu viel: Bei echter, komprimierter Musik ragt ein Kick
# selten um die Haelfte heraus. Gemessen an einem Signal mit
# durchgehendem Bass kamen damit 5 Schlaege in 20 Sekunden an, wo 40
# zu erwarten waren.
#
SCHLAG_FAKTOR = 1.25

#
# Dasselbe noch einmal fuer die Snare, auf dem Mittenband.
#
# Was hier gemeldet wird, ist KEINE erkannte Snare - das waere eine
# Instrumentenerkennung, und die ist mit drei Huellkurven nicht zu
# haben. Es ist ein scharfer, lauter Einsatz im Mittenband, der aus
# dem heraussticht, was gerade ueblich war. In den allermeisten
# Stuecken ist das die Snare; es kann auch ein Clap sein oder ein
# hart angeschlagener Akkord.
#
# Zwei Bedingungen, und sie sagen Verschiedenes:
#
#   AUSSCHLAG - es muss ein Einsatz sein und kein Dauerzustand,
#               gemessen am eigenen gleitenden Mittel.
#   SCHWELLE  - und er muss LAUT sein, gemessen an der laufenden
#               Spitze.
#
# Beide haengen am selben Regler, der Empfindlichkeit. Das war
# zuerst anders: Der Regler bewegte nur die Schwelle, der Ausschlag
# stand fest bei 2,5. Am Geraet zeigte sich, dass genau der bremst -
# es blitzte am Anfang eines Songs und wenn in einer ruhigen Stelle
# etwas Lautes passierte, aber nicht im laufenden Groove. Der Grund
# steckt in der Rechnung: Im Groove hebt die Snare ihr eigenes
# Bezugsmittel mit an und kommt nicht mehr um das 2,5-fache
# darueber. Nach einer leisen Stelle ist das Mittel niedrig, da
# ragt sie heraus. Wer die Schwelle allein herunterdreht, kommt
# daran nicht heran.
#
SNARE_EMPFINDLICHKEIT = 0.5

#
# Wo die beiden Zahlen bei genau dieser Empfindlichkeit stehen.
#
# Das ist der Stand, der am Geraet gefaellt: Der Regler sass dort am
# unteren Anschlag (Schwelle 0,2) bei fest eingebautem Ausschlag
# 2,5. Deshalb ist die Vorgabe die MITTE des neuen Reglers - nach
# dem Update klingt es genau wie vorher, und es gibt Luft in beide
# Richtungen.
#
SNARE_SCHWELLE = 0.2
SNARE_AUSSCHLAG = 2.5

#
# Die Enden des Reglers.
#
# Der Ausschlag darf nach unten nicht beliebig weit: Gemessen an
# einem gleichbleibenden Saegezahn - also an dem, was ein gehaltener
# Ton eines verzerrten Instruments der Analyse zeigt - kamen bei 1,3
# neun Fehlmeldungen in vier Sekunden durch, bei 2,5 fuenf, bei 3,5
# zwei. 1,3 ist damit das aeusserste, was noch vertretbar ist, und
# es steht am Anschlag "ganz empfindlich".
#
SNARE_SCHWELLE_MIN = 0.05
SNARE_SCHWELLE_MAX = 0.65

SNARE_AUSSCHLAG_MIN = 1.3
SNARE_AUSSCHLAG_MAX = 6.1


def snare_grenzen(empfindlichkeit: float) -> tuple[float, float]:
    """
    Schwelle und Ausschlag aus der Empfindlichkeit (0-1).

    Quadratisch, nicht linear: Die feine Abstufung gehoert an das
    empfindliche Ende, wo tatsaechlich eingestellt wird. Am strengen
    Ende reicht grob - dort geht es nur noch darum, wie sehr man
    zumacht.

    Die Anker sind so gewaehlt, dass die Mitte des Reglers genau
    SNARE_SCHWELLE und SNARE_AUSSCHLAG trifft.
    """

    streng = 1.0 - max(0.0, min(1.0, float(empfindlichkeit)))

    return (
        SNARE_SCHWELLE_MIN
        + (SNARE_SCHWELLE_MAX - SNARE_SCHWELLE_MIN) * streng ** 2,
        SNARE_AUSSCHLAG_MIN
        + (SNARE_AUSSCHLAG_MAX - SNARE_AUSSCHLAG_MIN) * streng ** 2,
    )

#
# Sperrzeit nach einer Snare. Laenger als beim Kick (0,12 s): Ein
# Blitz, der zweimal kurz hintereinander kommt, sieht nach Fehler
# aus, waehrend zwei Kicks nur zweimal Licht bedeuten.
#
SNARE_SPERRE_S = 0.15

#
# Wie viel von der laufenden Spitze in den Hoehen stehen muss, damit
# ein Ausschlag als Snare durchgeht - der "Knack" des Teppichs.
#
# Das ist die Bedingung, die den Kick aussortiert. Gemessen an einem
# Signal aus Kicks und Snares: Beim Kick lagen die Hoehen bei 0,04
# der Spitze, bei der Snare bei 0,65. Dazwischen ist viel Platz, die
# Schwelle muss nicht genau sitzen.
#
SNARE_HOEHEN_ANTEIL = 0.15

#
# Und wie viel Koerper dazugehoeren muss, gemessen an den Hoehen
# desselben Ausschlags.
#
# Das ist die Bedingung, die die Hi-Hat aussortiert: Die ist fast nur
# oben (Mitten zu Hoehen 0,3), eine Snare hat einen Rumpf (1,3).
#
# Bewusst die beiden Baender GEGENEINANDER und nicht gegen die
# laufende Spitze: Unter einer dicken Basslinie setzt der Bass die
# Spitze, und der Rumpf der Snare waere davon nur noch ein kleiner
# Bruchteil - die Bedingung haette dann von der Musik abgehangen
# statt von der Trommel.
#
SNARE_KOERPER_ANTEIL = 0.7

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
                 links: int = 0, rechts: int = 1,
                 snare_empfindlichkeit: float = SNARE_EMPFINDLICHKEIT):

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

        self.schlag_anstieg = _koeffizient(SCHLAG_ANSTIEG_S, self.rate)
        self.schlag_abfall = _koeffizient(SCHLAG_ABFALL_S, self.rate)

        self._tief = 0.0
        self._mitte = 0.0

        self.tief = 0.0
        self.mittel = 0.0
        self.hoch = 0.0

        #
        # Die flinke Huellkurve des Bassbandes, nur fuer Schlaege.
        #
        self.tief_schnell = 0.0

        #
        # Dieselben flinken Huellkurven auf Mitten und Hoehen, fuer
        # die Snare. Sie benutzen dieselben Zeitkonstanten: Was einen
        # Kick heraushebt, hebt auch einen Schlag auf das Fell heraus.
        #
        # Warum es BEIDE braucht, steht bei der Auswertung.
        #
        self.mitte_schnell = 0.0
        self.hoch_schnell = 0.0

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
        # Und die Gegenstuecke fuer Mitten und Hoehen.
        #
        self.mitte_mittel = 0.0
        self.hoch_mittel = 0.0
        self.snare_schwelle, self.snare_ausschlag = snare_grenzen(
            snare_empfindlichkeit
        )

        #
        # Sperrzeit nach einem Schlag, damit ein einzelner Kick nicht
        # dreimal gemeldet wird.
        #
        self.sperre_bis = 0.0
        self.snare_sperre_bis = 0.0
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

            faktor = (self.schlag_anstieg if tief > self.tief_schnell
                      else self.schlag_abfall)

            self.tief_schnell = tief + faktor * (self.tief_schnell - tief)

            faktor = (self.schlag_anstieg if mittel > self.mitte_schnell
                      else self.schlag_abfall)

            self.mitte_schnell = mittel + faktor * (self.mitte_schnell - mittel)

            faktor = (self.schlag_anstieg if hoch > self.hoch_schnell
                      else self.schlag_abfall)

            self.hoch_schnell = hoch + faktor * (self.hoch_schnell - hoch)

            summe += wert * wert

        #
        # Der Bass gegen seinen eigenen gleitenden Mittelwert: Ein
        # Schlag ist ein deutlicher Ausreißer nach oben, nicht ein
        # absoluter Wert.
        #
        dauer = len(mono) / self.rate
        self.zeit += dauer

        if (self.tief_schnell > self.bass_mittel * SCHLAG_FAKTOR
                and self.zeit >= self.sperre_bis):

            schlag = True
            self.sperre_bis = self.zeit + 0.12

        #
        # Der Mittelwert zieht ueber rund eine Sekunde nach: schnell
        # genug, um einem Lautstaerkewechsel zu folgen, langsam genug,
        # um nicht dem einzelnen Schlag hinterherzulaufen.
        #
        anteil = min(1.0, dauer / SCHLAG_MITTEL_S)

        self.bass_mittel += anteil * (self.tief_schnell - self.bass_mittel)

        #
        # Und dasselbe fuer die Snare - aber auf ZWEI Baendern.
        #
        # Das Mittenband allein reicht nicht. Ein Kick hat eine
        # steile Flanke, und die laesst auch die Mitten kurz
        # ausschlagen: Beim Ausprobieren meldete ein Signal aus
        # lauter Kicks OHNE jede Snare acht von acht Malen eine
        # Snare. Das Blitzlicht haette also auf der Bassdrum gezuckt.
        #
        # Was die beiden trennt, sind die Hoehen. Gemessen an
        # demselben Signal: Beim Kick standen sie bei 0,02, beim
        # Schlag auf die Snare bei 0,30 - der Teppich rauscht weit
        # oberhalb von 2 kHz, ein Kick hat dort nichts.
        #
        # Die vierte Bedingung sortiert die Hi-Hat aus: Die ist fast
        # nur oben, eine Snare hat einen Rumpf. Gemessen wurden
        # Mitten zu Hoehen 0,3 bei der Hi-Hat und 1,3 bei der Snare.
        #
        # In der Stille kann nichts durchkommen, ohne dass es dafuer
        # eine eigene Bedingung braucht: Die laufende Spitze faellt
        # nie unter SPITZE_MIN, und die Lautstaerke-Bedingung misst
        # gegen sie.
        #
        snare = False

        if (self.mitte_schnell > self.mitte_mittel * self.snare_ausschlag
                and self.mitte_schnell > self.spitze * self.snare_schwelle
                and self.hoch_schnell > self.spitze * SNARE_HOEHEN_ANTEIL
                and self.mitte_schnell > self.hoch_schnell * SNARE_KOERPER_ANTEIL
                and self.zeit >= self.snare_sperre_bis):

            snare = True
            self.snare_sperre_bis = self.zeit + SNARE_SPERRE_S

        self.mitte_mittel += anteil * (self.mitte_schnell - self.mitte_mittel)
        self.hoch_mittel += anteil * (self.hoch_schnell - self.hoch_mittel)

        self.pegel = math.sqrt(summe / len(mono))

        self.spitzen_nachfuehren()

        return self.stand(schlag, snare)

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

    def stand(self, schlag: bool = False, snare: bool = False) -> dict:
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

            #
            # Ein scharfer, lauter Einsatz im Mittenband - meist die
            # Snare. Siehe SNARE_FAKTOR.
            #
            "snare": snare,
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

      - Die Spracherkennung ist standardmäßig AUS (Wartezeit 0).

        Das ist eine Entscheidung aus dem Betrieb, keine Bequemlichkeit:
        "Kein Bassschlag" ist kein Beweis für eine Ansage. Eine
        Ballade, ein akustisches Set, eine lange Einleitung - alles
        kann eine Weile ohne erkennbaren Kick auskommen. Springt die
        Show dann mitten im Stück auf eine feste Szene, ist das der
        schlimmste denkbare Fehlgriff; sie hört nicht auf zu leuchten,
        sie leuchtet falsch, und niemand weiß warum. Genau das ist am
        Gerät passiert.

        Stille dagegen ist eindeutig messbar und bleibt an.

        Wer die Spracherkennung will, stellt eine Wartezeit ein - dann
        ist es eine bewusste Entscheidung und keine Überraschung.
    """

    def __init__(self, stille_schwelle: float = 0.02,
                 stille_sekunden: float = 6.0,
                 sprache_sekunden: float = 0.0):

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

        elif (self.sprache_sekunden > 0
              and self.ohne_schlag_seit >= self.sprache_sekunden):
            #
            # Kein Bass-Puls ueber lange Zeit, aber es kommt etwas:
            # moeglicherweise eine Ansage.
            #
            # Nur wenn ausdruecklich eingeschaltet (Wartezeit > 0).
            # Der Grund steht in der Klassendokumentation: "keine
            # Schlaege" ist kein verlaesslicher Beweis fuer Sprache.
            #
            self.zustand = "speech"

        else:
            self.zustand = "music"

        return self.zustand
