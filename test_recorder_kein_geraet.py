#!/usr/bin/env python3
"""
Prüft, dass ohne offenes Audiogerät nichts startet.

Anlass ist eine Meldung vom Gerät: XRack lief ohne angeschlossene
Konsole. Die Audio-Karte oben zeigte richtig ein rotes Kreuz - die
Soundcheck-Karte darunter meldete trotzdem "bereit", und der
Aufnahmeknopf ließ sich drücken.

Was dabei wirklich passierte, war schlimmer als die falsche Anzeige:

  - Der Schreiber legte eine echte Datei an, mit einem Wave64-Kopf
    über 0 Kanäle und 0 Hz. Sie bekam eine Nummer und stand in der
    Aufnahmeliste - unbrauchbar.
  - Der Lesethread startete. read() lieferte ohne PCM-Handle sofort
    None, die Schleife machte weiter, und das Ganze drehte sich bei
    voller Last im Kreis. Eine Aufnahme, die nichts aufnimmt, aber
    einen Kern auslastet.
  - Die Speicherbremse konnte nicht greifen: Mit 0 Kanälen ist die
    Datenrate 0, und ohne Datenrate gibt es keine Restzeit.

Geprüft wird deshalb beides: dass abgelehnt wird, UND dass dabei
nichts entsteht - keine Datei, kein Thread. Und der Gegenfall, damit
die Wache nicht einfach alles abschaltet.
"""

import sys
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

#
# alsaaudio gibt es nur auf dem Pi. Gebraucht wird hier nichts davon -
# das Backend ist eine Attrappe -, nur der Import muss klappen.
#
fake_alsaaudio = types.ModuleType("alsaaudio")
fake_alsaaudio.PCM_FORMAT_S16_LE = 0
fake_alsaaudio.PCM_FORMAT_S24_LE = 1
fake_alsaaudio.PCM_FORMAT_S32_LE = 2
fake_alsaaudio.PCM_CAPTURE = 0
fake_alsaaudio.PCM_PLAYBACK = 1
fake_alsaaudio.PCM_NORMAL = 0
sys.modules["alsaaudio"] = fake_alsaaudio

from core.status import RecorderState  # noqa: E402
from recorder.recorder import Recorder  # noqa: E402


class Backend:
    """
    Ein Interface, das geöffnet sein kann oder nicht.

    `opened` ist genau die Frage, die der echte AudioBackend
    beantwortet (siehe audio/audio_backend.py): Gibt es ein
    PCM-Handle? Ohne eines liefert read() nur None.
    """

    BYTES = 4
    RAHMEN = 32

    def __init__(self, opened: bool, channels: int = 4, rate: int = 48000):

        self.opened = opened
        self.channels = channels
        self.native_channels = channels
        self.rate = rate

        self._chunk = bytes(channels * self.BYTES * self.RAHMEN)

    def read(self):

        if not self.opened:
            #
            # Genau wie das echte Backend ohne Handle - und genau das
            # ist die leere Schleife, um die es geht.
            #
            return None

        time.sleep(0.005)
        return self._chunk

    def aufnahmebreite(self, data):
        return data


class Schreiber:
    """
    Merkt sich, ob er geöffnet wurde - das ist der Kern der Sache.

    Der echte Schreiber legt beim Öffnen die Datei an. Wird er
    gefragt, obwohl kein Gerät offen ist, liegt anschließend eine
    unbrauchbare Aufnahme im Verzeichnis.
    """

    def __init__(self):
        self.filename = None
        self.directory = Path(".")
        self.geoeffnet = 0
        self.geschrieben = 0
        self.geschlossen = 0

    def open(self, channels, sample_rate, bits_per_sample,
             name_prefix="", start_channel=1,
             trenner="-"):
        self.start_channel = start_channel
        self.geoeffnet += 1
        self.filename = f"attrappe-{channels}ch-{sample_rate}hz.w64"

    def write(self, data):
        self.geschrieben += 1

    def close(self):
        self.geschlossen += 1


# ====================================================================
# 1. Ohne offenes Gerät startet keine Aufnahme - und es entsteht
#    nichts
# ====================================================================

recorder = Recorder(Backend(opened=False))
recorder.writer = Schreiber()

assert recorder.bereit is False, (
    "Der Recorder hält sich für bereit, obwohl kein Gerät offen ist."
)

assert recorder.start() is False, (
    "Die Aufnahme wurde gestartet, obwohl kein Audiogerät offen ist."
)

assert recorder.writer.geoeffnet == 0, (
    "Es wurde eine Aufnahmedatei angelegt, obwohl kein Gerät offen ist - "
    "sie hätte einen Kopf über 0 Kanäle und 0 Hz und läge unbrauchbar im "
    "Aufnahmeverzeichnis."
)

assert recorder.recording is False, recorder.recording

assert recorder.stream_active is False, (
    "Der Lesethread läuft, obwohl es nichts zu lesen gibt - er würde "
    "leer im Kreis drehen."
)

assert recorder.current_filename == "", (
    f"Es steht ein Dateiname im Recorder: {recorder.current_filename!r}"
)

print("OK: Ohne Gerät keine Aufnahme, keine Datei, kein Thread")


# ====================================================================
# 2. Auch die Pegelprüfung und das Mithören der Lichtshow nicht
# ====================================================================

assert recorder.start_monitoring() is False, (
    "Die Pegelprüfung wurde gestartet, obwohl kein Gerät offen ist - die "
    "Anzeige bliebe leer, und niemand erfährt, warum."
)

assert recorder.monitoring is False, recorder.monitoring

assert recorder.start_analysis() is False, (
    "Das Mithören der Lichtshow wurde gestartet, obwohl kein Gerät offen "
    "ist."
)

assert recorder.stream_active is False, (
    "Nach den abgelehnten Starts läuft trotzdem ein Lesethread."
)

print("OK: Ohne Gerät auch keine Pegelprüfung und kein Mithören")


# ====================================================================
# 3. Mit Gerät läuft alles wie vorher
#
# Der wichtige Gegenfall: Eine Wache, die einfach alles ablehnt, wäre
# schlimmer als keine.
# ====================================================================

recorder = Recorder(Backend(opened=True))
recorder.writer = Schreiber()

assert recorder.bereit is True

assert recorder.start() is True, (
    "Mit offenem Gerät lässt sich keine Aufnahme starten - die Wache "
    "lehnt zu viel ab."
)

assert recorder.writer.geoeffnet == 1, recorder.writer.geoeffnet

time.sleep(0.3)

assert recorder.recording is True
assert recorder.writer.geschrieben > 0, (
    "Es wurde nichts geschrieben, obwohl die Aufnahme läuft."
)

recorder.stop()

assert recorder.recording is False
assert recorder.writer.geschlossen == 1, recorder.writer.geschlossen

recorder = Recorder(Backend(opened=True))
recorder.writer = Schreiber()

assert recorder.start_monitoring() is True
assert recorder.monitoring is True

recorder.stop_monitoring()

assert recorder.start_analysis() is True
recorder.stop_analysis()

print("OK: Mit Gerät laufen Aufnahme, Pegelprüfung und Mithören")


# ====================================================================
# 4. Das Gerät fällt mitten in der Aufnahme zu
#
# Dann darf die laufende Aufnahme nicht plötzlich als "kein Gerät"
# gelten - geschrieben wird ja noch. Sie wird beendet wie immer.
# ====================================================================

backend = Backend(opened=True)

recorder = Recorder(backend)
recorder.writer = Schreiber()

assert recorder.start() is True

time.sleep(0.2)

backend.opened = False

assert recorder.recording is True, (
    "Die laufende Aufnahme hat sich selbst abgeschaltet, als das Gerät "
    "zufiel - sie hat noch eine offene Datei und muss ordentlich "
    "beendet werden."
)

recorder.stop()

assert recorder.writer.geschlossen == 1, (
    "Die Datei wurde nicht geschlossen - ohne Abschluss fehlen ihr die "
    "Größenangaben im Kopf, und sie ist unlesbar."
)

print("OK: Ein zufallendes Gerät beendet die Aufnahme nicht unsauber")


# ====================================================================
# 5. Und der Zustand, den die Karte anzeigt
#
# Hier hing die gemeldete Falschauskunft: IDLE heißt "bereit", und
# ohne Gerät stand genau das da.
# ====================================================================

from core.application import Application  # noqa: E402


class Nur:
    """Ein Ding mit genau den Eigenschaften, die man ihm mitgibt."""

    def __init__(self, **eigenschaften):
        self.__dict__.update(eigenschaften)


def zustand(audio: bool, recording: bool = False,
            monitoring: bool = False, playing: bool = False) -> str:
    """
    Die ECHTE Entscheidung aus Application, nicht eine Kopie davon:
    Geprüft wird die Reihenfolge, und die steht nur an einer Stelle.

    Aufgerufen wird die Methode an einer nicht aufgebauten Anwendung -
    der Rest von update_status bräuchte psutil, ALSA und ein Pult,
    diese eine Entscheidung braucht drei Felder.
    """

    stand = Nur(audio=audio, recorder=None)

    selbst = object.__new__(Application)
    selbst.status = stand
    selbst.recorder = Nur(recording=recording, monitoring=monitoring)
    selbst.player = Nur(playing=playing)

    Application._recorder_zustand(selbst)

    return stand.recorder.value


assert zustand(audio=False) == "no_device", (
    "Ohne offenes Gerät meldet der Recorder weiterhin 'bereit'."
)

assert zustand(audio=True) == "idle"

assert zustand(audio=False, recording=True) == "recording", (
    "Eine laufende Aufnahme wird von 'kein Gerät' überschrieben - der "
    "Nutzer will dann sehen, dass noch geschrieben wird."
)

assert zustand(audio=False, monitoring=True) == "monitoring"
assert zustand(audio=False, playing=True) == "playback"

print("OK: Der gemeldete Zustand nennt das fehlende Interface")


print("Alle Tests ohne Audiogerät erfolgreich.")
