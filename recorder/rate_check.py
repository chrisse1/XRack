"""
Stimmt die eingestellte Samplerate?

XRack kann sie nicht erkennen. Mischpulte wie die X32/XAir-Serie
melden über USB immer den ganzen unterstützten Bereich, nicht ihre
laufende Clock - deshalb stellt der Nutzer sie von Hand ein (siehe
Application.set_mixer_sample_rate()).

Steht sie falsch, läuft trotzdem alles: Pegel, Aufnahme, Lichtshow.
Auffallen tut es erst beim Abhören, wenn die Aufnahme zu schnell oder
zu langsam ist - und dann ist der Abend vorbei.

Messen lässt es sich aber: Die Blöcke kommen im Takt der TATSÄCHLICHEN
Clock des Interfaces. Rahmen je Sekunde Wanduhr ist damit die wahre
Rate, ganz gleich, was eingestellt ist.

Bewusst wird hier nur gemessen und geurteilt, nichts umgestellt: Die
Rate ist eine Angabe über die Hardware, und die gehört dem Nutzer.
XRack sagt ihm, dass etwas nicht zusammenpasst.
"""

from time import monotonic


#
# Vier Byte je Abtastwert - so liest XRack von ALSA (24 Bit
# linksbündig in 32 Bit, siehe audio/audio_backend.py).
#
BYTES_JE_WERT = 4

#
# So lange wird mindestens gemessen, bevor überhaupt etwas gesagt
# wird. Kürzer wäre unzuverlässig: Der Lesethread bekommt seine
# Blöcke schubweise, und über eine halbe Sekunde gemittelt käme
# Unsinn heraus.
#
MINDESTZEIT_S = 3.0

#
# Ab wann die Rate als falsch gilt. Zwei Prozent sind viel mehr, als
# eine Clock je abweicht, und viel weniger als der kleinste Irrtum,
# den man machen kann (44,1 gegen 48 sind acht Prozent).
#
ABWEICHUNG = 0.02

#
# Die Raten, die XRack zulässt (siehe core/configuration.py). Für die
# Meldung wird auf die nächstgelegene gerundet - "gemessen 44107 Hz"
# hilft niemandem, "vermutlich 44100" schon.
#
UEBLICHE_RATEN = (44100, 48000, 88200, 96000)


class RateCheck:
    """
    Zählt Rahmen gegen die Uhr und vergleicht mit der Einstellung.

    Solange zu wenig gemessen wurde, gibt es kein Urteil - `stimmt()`
    liefert dann None. Das ist der wichtige Fall: Lieber nichts sagen
    als etwas Falsches.
    """

    def __init__(self, channels: int, erwartet: int):

        self.channels = max(1, int(channels))
        self.erwartet = max(1, int(erwartet))

        self._rahmen = 0
        self._beginn: float | None = None
        self._zuletzt: float | None = None

    # ----------------------------------------------------------------
    # Messen
    # ----------------------------------------------------------------

    def block(self, laenge: int, jetzt: float | None = None) -> None:
        """
        Einen gelesenen Block melden (`laenge` in Byte).

        Der ERSTE Block zählt nicht mit, nur seine Uhrzeit: In ihm
        steckt der Rückstau aus dem ALSA-Puffer, der sich seit dem
        Öffnen angesammelt hat. Er würde die Messung nach oben
        ziehen, und zwar genau am Anfang, wo sonst noch nichts
        mittelt.
        """

        if jetzt is None:
            jetzt = monotonic()

        if self._beginn is None:
            self._beginn = jetzt
            self._zuletzt = jetzt
            return

        rahmen = int(laenge) // (self.channels * BYTES_JE_WERT)

        if rahmen <= 0:
            return

        self._rahmen += rahmen
        self._zuletzt = jetzt

    def reset(self) -> None:
        """Von vorn messen - etwa nach einem Gerätewechsel."""

        self._rahmen = 0
        self._beginn = None
        self._zuletzt = None

    # ----------------------------------------------------------------
    # Urteilen
    # ----------------------------------------------------------------

    @property
    def dauer(self) -> float:
        """Wie lange schon gemessen wird."""

        if self._beginn is None or self._zuletzt is None:
            return 0.0

        return max(0.0, self._zuletzt - self._beginn)

    @property
    def gemessen(self) -> float:
        """
        Die gemessene Rate in Hz - 0.0, solange zu wenig Daten da
        sind.
        """

        if self.dauer < MINDESTZEIT_S or self._rahmen <= 0:
            return 0.0

        return self._rahmen / self.dauer

    @property
    def vermutet(self) -> int:
        """
        Die übliche Rate, die zur Messung passt - oder 0.

        Die 0 ist wichtig und nicht bloss ein Fehlwert: Wenn die
        Messung zu KEINER üblichen Rate passt (etwa 47000 Hz), liegt
        kein Irrtum bei der Einstellung vor, sondern es gehen Rahmen
        verloren - Aussetzer beim Lesen. Dann darf XRack nicht "stell
        auf 48000" raten, sondern muss sagen, was es sieht.
        """

        gemessen = self.gemessen

        if not gemessen:
            return 0

        naechste = min(UEBLICHE_RATEN, key=lambda rate: abs(rate - gemessen))

        if abs(naechste - gemessen) / naechste > ABWEICHUNG:
            return 0

        return naechste

    def stimmt(self) -> bool | None:
        """
        True, False - oder None, solange noch kein Urteil möglich ist.
        """

        gemessen = self.gemessen

        if not gemessen:
            return None

        return abs(gemessen - self.erwartet) / self.erwartet <= ABWEICHUNG

    def status(self) -> dict:
        """Was die Oberfläche braucht."""

        return {
            "expected": self.erwartet,
            "measured": round(self.gemessen, 1),
            "likely": self.vermutet,
            "plausible": self.stimmt(),
        }
