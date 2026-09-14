#!/usr/bin/env python3
"""
Prüft, dass XRack das Sampleformat anfordert, mit dem es rechnet.

Anlass ist eine Zeile, die im Protokoll des Geräts bei JEDEM Start
stand:

    WARNING | ALSA hat ein anderes Sampleformat akzeptiert als
              angefordert: gefordert 6, gemeldet 10.

6 ist S24_LE, 10 ist S32_LE. XRack forderte S24_LE an, der XR18
lieferte S32_LE - und die ganze Kette rechnet mit S32_LE: vier Byte je
Wert, 2^31 als Vollausschlag (recorder/level_meter.py,
core/stem_combiner.py, der Wave64-Kopf). Richtig herausgekommen ist es
also nur, weil das Interface etwas anderes gab als verlangt.

Zwei Dinge werden hier festgehalten:

  1. Angefordert wird S32_LE - auf der Aufnahme- UND auf der
     Wiedergabeseite. Auf einem Interface, das S24_LE tatsächlich
     annimmt, hätte der Soundcheck sonst aus den unteren 24 Bit
     gelesen, also aus dem Rauschen.
  2. Kommt etwas anderes zurück, ist das ein Befund: eine Meldung mit
     dem NAMEN des Formats (nicht der Zahl), dem Angebot des Geräts
     und der Folge - und ein Eintrag in der Selbstprüfung.
"""

#
# Der Suchpfad zur Projektwurzel - siehe tests/_wurzel.py. Muss VOR
# allen Importen aus XRack stehen.
#
from _wurzel import WURZEL  # noqa: F401,E402


import logging
import sys
import types
from pathlib import Path


#
# Die echten Zahlen von alsaaudio, damit die Namensauflösung geprüft
# wird und nicht eine Attrappe mit Wunschwerten.
#
fake_alsaaudio = types.ModuleType("alsaaudio")
fake_alsaaudio.PCM_FORMAT_S16_LE = 2
fake_alsaaudio.PCM_FORMAT_S24_LE = 6
fake_alsaaudio.PCM_FORMAT_S24_3LE = 32
fake_alsaaudio.PCM_FORMAT_S32_LE = 10
fake_alsaaudio.PCM_CAPTURE = 0
fake_alsaaudio.PCM_PLAYBACK = 1
fake_alsaaudio.PCM_NORMAL = 0


class FakePCM:
    """
    Ein Interface, das ein bestimmtes Format erzwingt - so wie ALSA es
    tut: setformat() liefert, was wirklich gesetzt wurde.
    """

    liefert = None

    def __init__(self, type, mode, device):
        self.gesetzt = None

    def setrate(self, rate):
        return rate

    def setchannels(self, channels):
        pass

    def setformat(self, fmt):
        self.gesetzt = fmt
        return FakePCM.liefert if FakePCM.liefert is not None else fmt

    def setperiodsize(self, size):
        pass

    def write(self, daten):
        #
        # ALSA nimmt den Block an; was daraus wird, prüft diese Datei
        # nicht. Gebraucht wird er, um den Puls mitzuzählen.
        #
        return len(daten)

    def close(self):
        pass


fake_alsaaudio.PCM = FakePCM
sys.modules["alsaaudio"] = fake_alsaaudio

from audio.audio_backend import (  # noqa: E402
    WUNSCHFORMAT,
    WUNSCHFORMAT_NAME,
    AudioBackend,
    formatname,
)
from audio.audio_playback_backend import AudioPlaybackBackend  # noqa: E402
from audio.models import AudioDevice  # noqa: E402


class Mitschrift(logging.Handler):
    """Sammelt, was XRack ins Protokoll schreibt."""

    def __init__(self):
        super().__init__()
        self.zeilen = []

    def emit(self, satz):
        self.zeilen.append((satz.levelname, satz.getMessage()))

    def text(self):
        return "\n".join(f"{stufe}: {zeile}" for stufe, zeile in self.zeilen)


def mitschreiben() -> Mitschrift:

    mit = Mitschrift()

    logger = logging.getLogger("XRack")
    logger.setLevel(logging.DEBUG)
    logger.handlers = [mit]

    return mit


GERAET = AudioDevice(
    card=0, device=0, name="X18/XR18", channels=18, sample_rate=48000,
)
GERAET.formats = ["S32_LE"]


# ====================================================================
# 1. Der Name statt der Zahl
# ====================================================================

assert formatname(fake_alsaaudio.PCM_FORMAT_S32_LE) == "S32_LE"
assert formatname(fake_alsaaudio.PCM_FORMAT_S24_LE) == "S24_LE"
assert formatname(fake_alsaaudio.PCM_FORMAT_S24_3LE) == "S24_3LE"

#
# Und etwas Unbekanntes wird nicht erfunden.
#
assert formatname(9999) == "9999"

assert WUNSCHFORMAT == fake_alsaaudio.PCM_FORMAT_S32_LE, (
    "XRack fordert nicht S32_LE an - genau das war der Fehler."
)

assert WUNSCHFORMAT_NAME == "S32_LE"

print("OK: Aus der ALSA-Zahl wird ein Name, und gewünscht ist S32_LE")


# ====================================================================
# 2. Aufnahme: S32_LE wird angefordert, und es gibt keine Warnung
#
# Die Warnung stand vorher bei JEDEM Start da und traf nicht zu. Eine
# Warnung, die immer erscheint, liest niemand mehr - und dann fehlt sie
# an dem Tag, an dem sie stimmt.
# ====================================================================

FakePCM.liefert = None

mit = mitschreiben()

backend = AudioBackend()

assert backend.open(GERAET, channels=18, rate=48000)

assert backend._pcm.gesetzt == fake_alsaaudio.PCM_FORMAT_S32_LE, (
    f"Angefordert wurde {formatname(backend._pcm.gesetzt)} statt S32_LE."
)

assert backend.sample_format == fake_alsaaudio.PCM_FORMAT_S32_LE

auffaellig = [
    zeile for stufe, zeile in mit.zeilen
    if stufe in ("WARNING", "ERROR")
]

assert not auffaellig, (
    "Beim passenden Format steht trotzdem eine Warnung im Protokoll:\n"
    + mit.text()
)

#
# Und die Selbstprüfung sagt, welches Format läuft.
#
pruefung = {teil.name: teil for teil in backend.diagnose()}

assert "Sampleformat" in pruefung, sorted(pruefung)
assert pruefung["Sampleformat"].ok is True
assert pruefung["Sampleformat"].message == "S32_LE", (
    pruefung["Sampleformat"].message
)

print("OK: Die Aufnahme fordert S32_LE an - ohne Warnung, mit Eintrag")


# ====================================================================
# 3. Liefert das Interface etwas anderes, ist das ein Befund
# ====================================================================

FakePCM.liefert = fake_alsaaudio.PCM_FORMAT_S24_3LE

GERAET.formats = ["S24_3LE", "S16_LE"]

mit = mitschreiben()

backend = AudioBackend()

assert backend.open(GERAET, channels=18, rate=48000), (
    "XRack öffnet das Gerät gar nicht mehr - es soll melden, nicht "
    "verweigern: Ein Interface, das etwas anderes liefert, ist besser "
    "als keines."
)

fehler = [zeile for stufe, zeile in mit.zeilen if stufe == "ERROR"]

assert fehler, (
    "Ein falsches Sampleformat steht nur als Nebenbemerkung im "
    "Protokoll:\n" + mit.text()
)

meldung = fehler[0]

assert "S24_3LE" in meldung, meldung
assert "S32_LE" in meldung, meldung

#
# Und was das Gerät überhaupt anbietet - sonst rät der Nutzer.
#
assert "S16_LE" in meldung, (
    f"Die Meldung nennt nicht, was das Gerät anbietet:\n{meldung}"
)

assert "6" not in meldung.replace("S16", "").replace("2^31", ""), (
    f"In der Meldung steht noch eine nackte ALSA-Zahl:\n{meldung}"
)

pruefung = {teil.name: teil for teil in backend.diagnose()}

assert pruefung["Sampleformat"].ok is False, (
    "Die Selbstprüfung meldet ein falsches Sampleformat als in Ordnung."
)

assert pruefung["Sampleformat"].message == "S24_3LE"

print("OK: Ein anderes Format wird mit Namen, Angebot und Folge gemeldet")


# ====================================================================
# 4. Die Wiedergabe fordert dasselbe an
#
# Hier stand als Vorgabe S24_LE, und nur der Soundcheck benutzte sie -
# Musik und Bluetooth gaben S32_LE ausdrücklich mit. Gespielt werden
# dabei aber genau die Aufnahmen, die als S32_LE geschrieben wurden.
# ====================================================================

FakePCM.liefert = None

GERAET.formats = ["S32_LE"]

mit = mitschreiben()

wiedergabe = AudioPlaybackBackend()

assert wiedergabe.open(GERAET, channels=18, rate=48000)

assert wiedergabe._pcm.gesetzt == fake_alsaaudio.PCM_FORMAT_S32_LE, (
    f"Der Soundcheck fordert {formatname(wiedergabe._pcm.gesetzt)} an - "
    f"gespielt werden aber S32_LE-Aufnahmen. Auf einem Interface, das "
    f"S24_LE annimmt, käme das Rauschen aus den unteren 24 Bit."
)

assert not [
    zeile for stufe, zeile in mit.zeilen if stufe in ("WARNING", "ERROR")
], mit.text()

#
# Eine ausdrücklich übergebene Wahl gilt weiterhin - Musik und
# Bluetooth geben ihr Format mit, und das soll so bleiben.
#
wiedergabe = AudioPlaybackBackend()

assert wiedergabe.open(
    GERAET, channels=2, rate=48000,
    sample_format=fake_alsaaudio.PCM_FORMAT_S16_LE,
)

assert wiedergabe._pcm.gesetzt == fake_alsaaudio.PCM_FORMAT_S16_LE, (
    "Ein ausdrücklich übergebenes Format wird übergangen."
)

print("OK: Die Wiedergabe fordert S32_LE an, eigene Angaben gelten weiter")


# ====================================================================
# Öffnen und Schließen werden gemessen
#
# Beides hält den GIL (pyalsaaudio gibt ihn weder in snd_pcm_open noch
# in der Aushandlung der Hardware-Parameter frei, siehe
# audio/geraetewache.py). Während dieser Zeit läuft im ganzen Prozess
# kein Python - auch der Webserver nicht. Am Gerät sah das so aus: "Das
# Interface war kurz nicht erreichbar, als ich einen Übemix starten
# wollte."
#
# Die Aufzeichnung kann einen solchen Stillstand messen, aber nur dann
# benennen, wenn diese Stellen ihn auch melden. Deshalb steht das hier
# und nicht nur in test_diagnostics.py: Dort wird die Wache geprüft,
# hier, dass der echte Weg sie überhaupt betritt.
# ====================================================================

from audio.geraetewache import GERAETEWACHE  # noqa: E402


class LangsamePCM(FakePCM):
    """Ein Gerät, dessen Öffnen dauert - wie eines am USB."""

    def __init__(self, *args, **kwargs):
        #
        # Die Wache wird VOR dem Konstruktor betreten; hier muss also
        # schon zu sehen sein, dass etwas läuft.
        #
        LangsamePCM.gesehen = GERAETEWACHE.laufend()
        super().__init__(*args, **kwargs)


LangsamePCM.gesehen = None

fake_alsaaudio.PCM = LangsamePCM

try:

    wiedergabe = AudioPlaybackBackend()

    assert wiedergabe.open(GERAET, channels=2, rate=48000)

    assert LangsamePCM.gesehen is not None, (
        "Während des Öffnens weiß die Gerätewache von nichts - dann "
        "kann die Aufzeichnung einen Stillstand zwar messen, aber nicht "
        "sagen, was ihn verursacht hat."
    )

    assert "Wiedergabegerät öffnen" in LangsamePCM.gesehen, (
        f"Die Gerätewache nennt etwas anderes: {LangsamePCM.gesehen!r}"
    )

    assert GERAET.id in LangsamePCM.gesehen, (
        f"Das Gerät wird nicht benannt: {LangsamePCM.gesehen!r}"
    )

    #
    # Und der Puls: Jeder geschriebene Block wird gezählt. Ohne diese
    # Zählung kann die Aufzeichnung nicht entscheiden, ob während eines
    # Stillstands Ton geflossen ist - und genau das unterscheidet "der
    # ganze Prozess stand" von "nur der Webserver stand".
    #
    vorher = GERAETEWACHE.bloecke

    wiedergabe.write(b"\x00" * (4 * 2 * 64))

    assert GERAETEWACHE.bloecke == vorher + 1, (
        "Ein geschriebener Block wird nicht gezählt."
    )

    assert GERAETEWACHE.tonzeit(94) is not None, (
        "Die Blockdauer wurde beim Öffnen nicht gemeldet - dann lassen "
        "sich Blöcke nicht in Sekunden Ton umrechnen."
    )

    #
    # Nach dem Öffnen läuft nichts mehr - sonst stünde bei jedem
    # späteren Stillstand dieselbe alte Meldung.
    #
    assert GERAETEWACHE.laufend() is None, GERAETEWACHE.laufend()

    assert "Wiedergabegerät öffnen" in (GERAETEWACHE.letzte() or ""), (
        "Das abgeschlossene Öffnen wurde nicht festgehalten."
    )

    #
    # Und das Schließen ebenso - es ist die zweite Hälfte des Befunds.
    #
    class SchliessendePCM(LangsamePCM):

        def close(self):
            SchliessendePCM.beim_schliessen = GERAETEWACHE.laufend()

    SchliessendePCM.beim_schliessen = None

    wiedergabe._pcm = SchliessendePCM(
        type=fake_alsaaudio.PCM_PLAYBACK,
        mode=fake_alsaaudio.PCM_NORMAL,
        device=GERAET.id,
    )

    wiedergabe.close()

    assert SchliessendePCM.beim_schliessen is not None, (
        "Das Schließen wird nicht gemessen - dabei klemmt es am Gerät "
        "beim Stoppen genauso wie beim Starten."
    )

    assert "schließen" in SchliessendePCM.beim_schliessen, (
        f"Beim Schließen meldet die Wache etwas anderes: "
        f"{SchliessendePCM.beim_schliessen!r}"
    )

finally:
    fake_alsaaudio.PCM = FakePCM

print("OK: Öffnen und Schließen melden sich bei der Gerätewache")


print("Alle Sampleformat-Tests erfolgreich.")
