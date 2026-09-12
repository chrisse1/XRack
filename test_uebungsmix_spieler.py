#!/usr/bin/env python3
"""
Prüft, dass der Musikspieler Übungsmixe abspielen kann.

Zum Üben braucht man, was der Musikspieler kann und der
Soundcheck-Spieler nicht: anhalten, spulen, wiederholen. Also soll er
künftig auch die Übungsmixe spielen.

Der Haken, den dieser Versuch festhält: **ffmpeg liest XRacks eigene
Wave64-Dateien falsch.** Der Kopf ist in Ordnung (32-Bit-Behälter, 24
gültige Bits, BlockAlign = Kanäle * 4), ffmpeg entscheidet sich
trotzdem für `pcm_s24le` und liest drei Byte je Wert, wo vier stehen.
Aus zwei Sekunden werden 2,67, jeder Kanal landet woanders, und zu
hören wäre Rauschen.

Deshalb liest XRack seine eigenen Dateien selbst. Hier wird gemessen,
dass das nötig ist und dass es stimmt - mit einer echten Datei, die
XRacks eigener Schreiber anlegt, nicht mit einer Attrappe.
"""

import math
import struct
import subprocess
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

fake_alsaaudio = types.ModuleType("alsaaudio")
for name in (
    "PCM_FORMAT_S16_LE", "PCM_FORMAT_S24_LE", "PCM_FORMAT_S32_LE",
    "PCM_CAPTURE", "PCM_PLAYBACK", "PCM_NORMAL",
):
    setattr(fake_alsaaudio, name, 0)
sys.modules["alsaaudio"] = fake_alsaaudio

from audio.models import AudioDevice  # noqa: E402
from core.recording_kind import MARKER_PRACTICE  # noqa: E402
from player.music_library import MusicLibrary  # noqa: E402
from player.music_player import MusicPlayer  # noqa: E402
from player.w64_decoder import (  # noqa: E402
    W64Decoder,
    eckdaten,
    liest_xrack_selbst,
)
from writer.w64_writer import W64Writer  # noqa: E402

KANAELE = 8
RATE = 48000
SEKUNDEN = 1
RAHMEN = KANAELE * 4


def uebungsmix(ordner: Path) -> Path:
    """
    Ein echter Übungsmix, wie XRack ihn schreibt - jeder Kanal mit
    seinem eigenen Wert, damit jede Verschiebung auffällt.
    """

    schreiber = W64Writer()
    schreiber.directory = ordner

    schreiber.open(
        channels=KANAELE,
        sample_rate=RATE,
        bits_per_sample=24,
        name_prefix="Pruefmix",
        marker=MARKER_PRACTICE,
    )

    block = bytearray()

    for n in range(RATE * SEKUNDEN):
        for kanal in range(KANAELE):
            #
            # Kanal k traegt konstant den Wert (k+1) * 1000000 - eine
            # Verschiebung um einen Kanal ist damit sofort sichtbar.
            #
            block += struct.pack("<i", (kanal + 1) * 1000000)

    schreiber.write(bytes(block))
    schreiber.close()

    return Path(schreiber.filename)


arbeit = tempfile.TemporaryDirectory()
ORDNER = Path(arbeit.name)

DATEI = uebungsmix(ORDNER)


# ====================================================================
# 1. ffmpeg liest unsere Dateien falsch - deshalb gibt es den
#    eigenen Dekoder
#
# Wenn dieser Abschnitt eines Tages fällt, weil ffmpeg es gelernt hat:
# Umso besser, dann kann player/w64_decoder.py verschwinden. Bis dahin
# ist er die Begründung dafür, dass es ihn gibt.
# ====================================================================

erwartete_bytes = RATE * SEKUNDEN * RAHMEN

assert DATEI.stat().st_size > erwartete_bytes, DATEI.stat().st_size

lauf = subprocess.run(
    ["ffmpeg", "-v", "error", "-i", str(DATEI),
     "-f", "s32le", "-acodec", "pcm_s32le",
     "-ar", str(RATE), "-ac", str(KANAELE), "-"],
    capture_output=True,
    timeout=60,
)

if lauf.returncode == 0 and len(lauf.stdout) == erwartete_bytes:

    print("HINWEIS: ffmpeg liest die Datei inzwischen richtig - "
          "player/w64_decoder.py könnte entfallen.")

else:

    print(
        f"OK: ffmpeg liest unsere Datei falsch "
        f"({len(lauf.stdout)} statt {erwartete_bytes} Byte) - "
        f"darum liest XRack sie selbst"
    )


# ====================================================================
# 2. XRacks eigener Dekoder liest sie richtig
# ====================================================================

assert liest_xrack_selbst(DATEI)
assert not liest_xrack_selbst(Path("lied.mp3"))

daten = eckdaten(DATEI)

assert daten["channels"] == KANAELE, daten
assert daten["rate"] == RATE, daten
assert abs(daten["duration"] - SEKUNDEN) < 0.01, (
    f"Die Länge stimmt nicht: {daten['duration']} statt {SEKUNDEN} - "
    f"gerechnet wurde vermutlich mit drei Byte je Wert statt vier."
)

dekoder = W64Decoder()

assert dekoder.open(DATEI, channels=KANAELE, rate=RATE)

gelesen = b""

while True:
    teil = dekoder.read(1 << 16)
    if teil is None:
        break
    gelesen += teil

dekoder.close()

assert len(gelesen) == erwartete_bytes, (
    f"{len(gelesen)} statt {erwartete_bytes} Byte gelesen."
)

werte = [
    struct.unpack("<i", gelesen[kanal * 4:(kanal + 1) * 4])[0]
    for kanal in range(KANAELE)
]

assert werte == [(kanal + 1) * 1000000 for kanal in range(KANAELE)], (
    f"Die Kanäle liegen falsch: {werte} - jede Verschiebung heisst, "
    f"dass der Bass auf der Stimme landet."
)

print("OK: XRacks Dekoder liefert die Kanäle unverschoben")


# ====================================================================
# 3. Spulen landet an der richtigen Stelle
#
# Beim Üben will man eine Stelle wiederholen - das ist der Grund für
# den ganzen Umbau.
# ====================================================================

dekoder = W64Decoder()

assert dekoder.open(DATEI, channels=KANAELE, rate=RATE, start_position=0.5)

rest = b""

while True:
    teil = dekoder.read(1 << 16)
    if teil is None:
        break
    rest += teil

dekoder.close()

assert len(rest) == erwartete_bytes // 2, (
    f"Nach dem Sprung auf die Hälfte kamen {len(rest)} Byte statt "
    f"{erwartete_bytes // 2} - der Sprung landete woanders."
)

#
# Und er landet auf einem Rahmenanfang, nicht mittendrin: Sonst waeren
# ab dort alle Kanaele um einen Wert verschoben.
#
werte = [
    struct.unpack("<i", rest[kanal * 4:(kanal + 1) * 4])[0]
    for kanal in range(KANAELE)
]

assert werte == [(kanal + 1) * 1000000 for kanal in range(KANAELE)], (
    f"Nach dem Sprung stehen die Kanäle verschoben: {werte}"
)

print("OK: Ein Sprung landet auf einem Rahmenanfang")


# ====================================================================
# 4. Der Musikspieler nimmt die Kanalzahl aus der Datei
#
# Musik ist Stereo, ein Übungsmix nicht. Öffnete der Spieler das
# Interface mit zwei Kanälen, landete ein Acht-Kanal-Mix als Brei auf
# den ersten beiden.
# ====================================================================

class Ausgang:
    """
    Ein Interface, das sich Zeit lässt.

    Das Bremsen ist wichtig: Ein echtes ALSA-Gerät nimmt die Blöcke im
    Takt der Samplerate an. Ein Ausgang, der alles sofort schluckt,
    spielt eine Sekunde Material in Millisekunden ab - der Titel wäre
    vorbei, bevor der Versuch hinsieht, und geprüft würde nichts.
    """

    def __init__(self, takt=0.004):
        self.geoeffnet = []
        self.opened = False
        self.geschrieben = 0
        self.takt = takt

    def open(self, device, channels, rate, start_channel=0,
             sample_format=None):
        self.geoeffnet.append((channels, rate, start_channel))
        self.opened = True
        return True

    def write(self, daten):
        import time as _t
        _t.sleep(self.takt)
        self.geschrieben += len(daten)

    def close(self):
        self.opened = False


import time  # noqa: E402


def warte_auf(bedingung, frist=5.0, was=""):
    """
    Wartet, bis etwas WIRKLICH eingetreten ist.

    Feste Wartezeiten waren hier der Fehler: track_duration steht
    schon, bevor der Lesethread den Titel geöffnet hat - wer darauf
    wartet und dann stoppt, hat nie etwas geschrieben. Unter Last
    fiel dieser Versuch dadurch in zwei von drei Läufen.
    """

    ende = time.monotonic() + frist

    while time.monotonic() < ende:

        if bedingung():
            return True

        time.sleep(0.01)

    raise AssertionError(f"Nach {frist} s nicht eingetreten: {was}")


geraet = AudioDevice(
    card=0, device=0, name="X18/XR18", channels=18, sample_rate=RATE,
)

ausgang = Ausgang()

spieler = MusicPlayer(ausgang, MusicLibrary(ORDNER))

assert spieler.play_practice(
    geraet, DATEI, start_channel=0, rate=RATE
), "Der Übungsmix liess sich nicht starten."

#
# Warten, bis wirklich Ton fliesst - nicht bloss, bis die Laenge
# dasteht: Die steht schon, bevor der Lesethread die Datei geoeffnet
# hat.
#
warte_auf(lambda: ausgang.geschrieben > 0, was="der erste Block")

kanaele, rate, start = ausgang.geoeffnet[0]

assert kanaele == KANAELE, (
    f"Der Spieler öffnet das Interface mit {kanaele} Kanälen - der "
    f"Übungsmix hat aber {KANAELE}. Er landete als Brei auf den ersten "
    f"beiden."
)

assert rate == RATE and start == 0, (rate, start)

assert abs(spieler.track_duration - SEKUNDEN) < 0.05, (
    f"Die Länge des Übungsmixes: {spieler.track_duration}"
)

#
# Und der Titel steht da - ohne ffprobe, aus dem Dateinamen.
#
assert spieler.current_track_title == DATEI.stem, (
    spieler.current_track_title
)

spieler.stop()

assert ausgang.geschrieben > 0, "Es wurde nichts ans Interface geschrieben."

print(f"OK: Der Spieler öffnet {KANAELE} Kanäle und spielt den Mix")


# ====================================================================
# 5. Die Schleife
#
# Beim Üben spielt man dieselbe Stelle immer wieder. Ohne Schleife
# endet der Mix und man drückt jedes Mal neu.
# ====================================================================

ausgang = Ausgang()

spieler = MusicPlayer(ausgang, MusicLibrary(ORDNER))

assert spieler.play_practice(
    geraet, DATEI, start_channel=0, rate=RATE, wiederholen=True
)

assert spieler.wiederholen is True

#
# Eine Sekunde Material - es muss mehr als einmal durchlaufen.
#
warte_auf(
    lambda: ausgang.geschrieben > erwartete_bytes,
    frist=10.0,
    was=(
        "ein zweiter Durchlauf (bei laufender Schleife muss mehr als "
        f"{erwartete_bytes} Byte zusammenkommen)"
    ),
)

assert spieler.playing, (
    "Nach dem Ende des Stücks ist die Wiedergabe vorbei, obwohl die "
    "Schleife eingeschaltet war."
)

spieler.set_wiederholen(False)

assert spieler.wiederholen is False

spieler.stop()

print("OK: Mit Schleife läuft der Mix weiter, ohne endet er")


arbeit.cleanup()

print("Alle Tests zum Übungsmix-Spieler erfolgreich.")
