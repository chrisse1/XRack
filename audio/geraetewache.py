"""
Hält fest, wann XRack ein Audiogerät öffnet oder schließt - und wie
lange es gedauert hat.

Der Anlass ist ein Befund vom Gerät, der lange wie ein Netzproblem
aussah: "Das Interface war wieder kurz nicht erreichbar, als ich einen
Übemix starten wollte. Ich habe das Gefühl, es passiert immer, wenn ich
eine Wiedergabe starten oder stoppen will."

Der Verdacht liegt nicht im Netz, sondern im GIL. Nachgesehen im
Quelltext von pyalsaaudio 0.11.0 (alsaaudio.c):

  - Der Konstruktor ruft snd_pcm_open() OHNE Py_BEGIN_ALLOW_THREADS.
  - alsapcm_setup() - die Aushandlung der Hardware-Parameter, die
    hinter setrate(), setchannels(), setformat() und setperiodsize()
    steckt - enthält ebenfalls kein einziges ALLOW_THREADS.
  - close() gibt den GIL für snd_pcm_drain() frei, für snd_pcm_close()
    aber nicht.

Lesen und Schreiben geben ihn frei (Py_BEGIN_ALLOW_THREADS um
snd_pcm_readi/writei) - im laufenden Betrieb ist also alles gut. Aber
solange ein Gerät geöffnet oder geschlossen wird, läuft in diesem
Prozess KEIN Python: kein Webserver, keine Statusabfrage, nichts. XRack
öffnet dabei nicht einmal, sondern löst fünf Aushandlungen aus (PCM()
und die vier Setter).

Das erklärt genau das Bild: Es passiert beim Starten und beim Stoppen,
es geht von selbst vorbei, im Protokoll steht nichts, und der Dienst ist
nie abgestürzt.

Ob es wirklich die Ursache ist, sagt aber erst eine Messung am Gerät -
deshalb diese Datei. Sie tut nichts weiter, als mitzuschreiben, was
gerade geöffnet wird und wie lange es gedauert hat. Die Aufzeichnung
(core/diagnostics.py) fragt hier nach, wenn sie einen Stillstand
bemerkt, und kann dann sagen, WAS in dieser Zeit lief.
"""

import threading
import time
from contextlib import contextmanager


class Geraetewache:
    """
    Ein Merkzettel: Was wird gerade am Audiogerät getan, und was war
    das letzte, das gedauert hat?

    Bewusst ohne Protokollierung und ohne Datei - sie wird aus dem
    Lesethread und aus Anfrage-Threads betreten, und was hier teuer
    wäre, verfälschte die Messung.
    """

    def __init__(self):

        self._sperre = threading.Lock()

        #
        # (Beschreibung, Beginn) der laufenden Arbeit, oder None.
        #
        self._laufend: tuple[str, float] | None = None

        #
        # (Beschreibung, Dauer, Ende) der letzten abgeschlossenen.
        #
        self._letzte: tuple[str, float, float] | None = None

        #
        # Die längste je gemessene Dauer - sie ist der Wert, der in
        # einen Fehlerbericht gehört.
        #
        self._laengste: tuple[str, float] | None = None

    @contextmanager
    def arbeit(self, was: str):
        """
        Umschließt einen Zugriff, der den Prozess anhalten kann.

        Wird auch bei einem Fehlschlag sauber beendet: Ein Öffnen, das
        mit einer Ausnahme endet, hat trotzdem Zeit gekostet - und
        gerade das will man sehen.
        """

        beginn = time.monotonic()

        with self._sperre:
            self._laufend = (was, beginn)

        try:
            yield

        finally:

            ende = time.monotonic()
            dauer = ende - beginn

            with self._sperre:

                self._laufend = None
                self._letzte = (was, dauer, ende)

                if self._laengste is None or dauer > self._laengste[1]:
                    self._laengste = (was, dauer)

    def laufend(self) -> str | None:
        """Was gerade läuft, samt bisheriger Dauer - oder None."""

        with self._sperre:

            if self._laufend is None:
                return None

            was, beginn = self._laufend

        return f"{was} (läuft seit {time.monotonic() - beginn:.1f} s)"

    def letzte(self, nicht_aelter_als: float = 0.0) -> str | None:
        """
        Die zuletzt abgeschlossene Arbeit - oder None.

        `nicht_aelter_als` grenzt sie zeitlich ein: Für die Frage "was
        lief während des Stillstands" ist ein Öffnen von vor zehn
        Minuten keine Antwort.
        """

        with self._sperre:

            if self._letzte is None:
                return None

            was, dauer, ende = self._letzte

        if nicht_aelter_als and time.monotonic() - ende > nicht_aelter_als:
            return None

        return f"{was} ({dauer:.1f} s, gerade beendet)"

    def laengste(self) -> str | None:
        """Die längste je gemessene Dauer - für die Schlusszeile."""

        with self._sperre:

            if self._laengste is None:
                return None

            was, dauer = self._laengste

        return f"{was}: {dauer:.1f} s"


#
# Eine für den ganzen Prozess. Es gibt genau ein Audiogerät und einen
# GIL - zwei Wachen hätten nichts zu trennen.
#
GERAETEWACHE = Geraetewache()
