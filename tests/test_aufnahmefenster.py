#!/usr/bin/env python3
"""
Prüft das Aufnahmefenster: ab Kanal X, so viele Kanäle.

Aufgenommen wurde bisher immer ab Kanal 1. Am X32 schleppt man dadurch
sechzehn leere Spuren mit, wenn man nur die Kanäle 17-24 braucht - und
beim Üben lässt sich das eigene Instrument gar nicht allein
mitschneiden.

Drei Dinge müssen stimmen, und das dritte ist das, was sonst niemandem
auffällt:

  1. Geschnitten wird genau das Fenster - kein Versatz, keine
     Nachbarkanäle.
  2. Der erste Kanal reist mit der Datei: Er steht im Namen, wie schon
     die Art der Aufnahme (core/recording_kind.py).
  3. Beim virtuellen Soundcheck landet die Aufnahme wieder auf
     DENSELBEN Kanälen. Ohne das käme der Ton aus den falschen Wegen
     des Pults - ohne Fehlermeldung, bis jemand hinhört.
"""

#
# Der Suchpfad zur Projektwurzel - siehe tests/_wurzel.py. Muss VOR
# allen Importen aus XRack stehen.
#
from _wurzel import WURZEL  # noqa: F401,E402


import sys
from pathlib import Path


from audio.channel_extractor import ChannelExtractor  # noqa: E402
from audio.channel_inserter import ChannelInserter  # noqa: E402
from core.recording_kind import (  # noqa: E402
    MARKER_PRACTICE,
    MARKER_SOUNDCHECK,
    kind_from_filename,
    marker_mit_kanal,
    start_channel_from_filename,
    strip_marker,
)

BYTES = 4
INTERFACE = 18


def rahmen(werte: dict[int, int]) -> bytes:
    """
    Ein Rahmen des Interfaces, in dem die genannten Kanäle (0-basiert)
    ihren Wert tragen und alle übrigen null sind.
    """

    roh = bytearray(INTERFACE * BYTES)

    for kanal, wert in werte.items():
        roh[kanal * BYTES] = wert

    return bytes(roh)


def kanalwerte(daten: bytes, kanaele: int) -> list[int]:
    """Die Werte eines Rahmens, ein Eintrag je Kanal."""

    return [daten[kanal * BYTES] for kanal in range(kanaele)]


# ====================================================================
# 1. Das Fenster schneidet genau das Fenster
# ====================================================================

#
# Jeder Kanal traegt seine eigene Nummer - dann faellt jeder Versatz
# sofort auf, statt sich als "irgendwie leise" zu tarnen.
#
voll = rahmen({kanal: kanal + 1 for kanal in range(INTERFACE)})

for start, breite, erwartet in (
    (0, 18, list(range(1, 19))),
    (0, 4, [1, 2, 3, 4]),
    (8, 4, [9, 10, 11, 12]),
    (16, 2, [17, 18]),
    (2, 2, [3, 4]),
):

    schneider = ChannelExtractor(
        input_channels=INTERFACE,
        output_channels=breite,
        start_channel=start,
    )

    ergebnis = schneider.extract(voll)

    assert len(ergebnis) == breite * BYTES, (
        f"ab Kanal {start + 1}, {breite} Kanäle: {len(ergebnis)} Byte "
        f"statt {breite * BYTES}"
    )

    assert kanalwerte(ergebnis, breite) == erwartet, (
        f"ab Kanal {start + 1}, {breite} Kanäle: "
        f"{kanalwerte(ergebnis, breite)} statt {erwartet} - das ist ein "
        f"Versatz, und im Ton hört man ihn als falschen Kanal."
    )

print("OK: Das Fenster schneidet genau die gewählten Kanäle heraus")


#
# Ueber mehrere Rahmen hinweg darf sich nichts verschieben - das war
# der alte Fehler, der zu wandernden Kanaelen fuehrte.
#
strom = b"".join(
    rahmen({kanal: (kanal + 1) for kanal in range(INTERFACE)})
    for _ in range(50)
)

schneider = ChannelExtractor(INTERFACE, 4, start_channel=8)

ergebnis = schneider.extract(strom)

assert len(ergebnis) == 50 * 4 * BYTES, len(ergebnis)

for nummer in range(50):

    block = ergebnis[nummer * 4 * BYTES:(nummer + 1) * 4 * BYTES]

    assert kanalwerte(block, 4) == [9, 10, 11, 12], (
        f"Rahmen {nummer}: {kanalwerte(block, 4)} - ab hier wandern die "
        f"Kanäle."
    )

print("OK: Auch über 50 Rahmen wandert nichts")


# ====================================================================
# 2. Ein Fenster, das über das Interface hinausragt
#
# Es abzuschneiden ist besser, als daneben zu greifen: Was zu weit
# rechts anfinge, läse in den nächsten Rahmen hinein - die Aufnahme
# wäre nicht leer, sondern verschoben.
# ====================================================================

ueberstand = ChannelExtractor(INTERFACE, 4, start_channel=16)

ergebnis = ueberstand.extract(voll)

assert len(ergebnis) == 4 * BYTES, len(ergebnis)

assert kanalwerte(ergebnis, 4) == [17, 18, 0, 0], (
    f"Über den Rand hinaus: {kanalwerte(ergebnis, 4)} - dort darf nur "
    f"Stille stehen, nichts aus dem nächsten Rahmen."
)

#
# Und ein Start jenseits des Interfaces wird an den Rand gezogen,
# statt ins Leere zu greifen.
#
daneben = ChannelExtractor(INTERFACE, 2, start_channel=99)

assert daneben.start_channel == INTERFACE - 1, daneben.start_channel

print("OK: Ein zu weites Fenster bleibt still statt zu verrutschen")


# ====================================================================
# 3. Der erste Kanal reist mit der Datei
# ====================================================================

assert marker_mit_kanal(MARKER_SOUNDCHECK) == "s"
assert marker_mit_kanal(MARKER_SOUNDCHECK, 1) == "s"
assert marker_mit_kanal(MARKER_SOUNDCHECK, 9) == "s9"
assert marker_mit_kanal(MARKER_PRACTICE, 17) == "p17"

for name, art, kanal in (
    ("Soundcheck-1_s.w64", "soundcheck", 1),
    ("Soundcheck-2_s9.w64", "soundcheck", 9),
    ("Probe-4_s17.w64", "soundcheck", 17),
    ("Song-1_p.w64", "practice", 1),
    #
    # Aeltere Aufnahmen ganz ohne Kuerzel - sie meinen Kanal 1 und
    # gelten als Soundcheck. Daran darf sich nie etwas aendern.
    #
    ("Alt-3.w64", "soundcheck", 1),
    ("Workshop.w64", "soundcheck", 1),
):

    assert kind_from_filename(name) == art, (name, kind_from_filename(name))

    assert start_channel_from_filename(name) == kanal, (
        f"{name}: erkannt als Kanal {start_channel_from_filename(name)} "
        f"statt {kanal}"
    )

#
# Und der Zaehler fuer die naechste Nummer muss das Kuerzel samt Kanal
# abstreifen koennen - sonst faengt er wieder bei 1 an und ueber-
# schreibt die vorhandene Aufnahme.
#
for stem, nackt in (
    ("Soundcheck-1_s", "Soundcheck-1"),
    ("Soundcheck-2_s9", "Soundcheck-2"),
    ("Probe-4_s17", "Probe-4"),
    ("Song-1_p", "Song-1"),
    ("Alt-3", "Alt-3"),
    ("12_s9", "12"),
):
    assert strip_marker(stem) == nackt, (stem, strip_marker(stem))

print("OK: Der erste Kanal steht im Namen, alte Namen bleiben gültig")


# ====================================================================
# 4. Der Rundlauf: aufgenommen ab Kanal 9, gespielt ab Kanal 9
#
# Das ist der Fall, der zählt. Landet die Aufnahme beim Soundcheck
# wieder auf Kanal 1, kommt der Ton aus den falschen Wegen des Pults -
# und zwar ohne dass irgendwo ein Fehler stünde.
# ====================================================================

aufnahme = ChannelExtractor(INTERFACE, 4, start_channel=8).extract(voll)

#
# So heisst die Datei, die dabei entsteht ...
#
dateiname = f"Probe-1_{marker_mit_kanal(MARKER_SOUNDCHECK, 9)}.w64"

assert dateiname == "Probe-1_s9.w64", dateiname

#
# ... und so wird sie wieder abgespielt: Der Spieler liest den Kanal
# aus dem Namen (siehe player/player.py).
#
zurueck = ChannelInserter(
    input_channels=4,
    output_channels=INTERFACE,
    start_channel=start_channel_from_filename(dateiname) - 1,
).insert(aufnahme)

werte = kanalwerte(zurueck, INTERFACE)

assert werte[8:12] == [9, 10, 11, 12], (
    f"Die Aufnahme landet auf den Kanälen {werte} - erwartet waren die "
    f"Werte 9-12 auf den Kanälen 9-12."
)

assert werte[:8] == [0] * 8 and werte[12:] == [0] * 6, (
    f"Neben dem Fenster steht etwas: {werte}"
)

print("OK: Ab Kanal 9 aufgenommen, ab Kanal 9 wiedergegeben")


#
# Gegenprobe zur Gegenprobe: OHNE die Kanalangabe im Namen landet
# dieselbe Aufnahme auf Kanal 1 - genau der Fehler, den der Name
# verhindert.
#
falsch = ChannelInserter(
    input_channels=4,
    output_channels=INTERFACE,
    start_channel=start_channel_from_filename("Probe-1_s.w64") - 1,
).insert(aufnahme)

assert kanalwerte(falsch, INTERFACE)[:4] == [9, 10, 11, 12], (
    "Ohne Kanalangabe müsste die Aufnahme auf Kanal 1 landen - dass "
    "das hier nicht so ist, heisst, dass der Versuch nichts zeigt."
)

print("OK: Ohne Kanalangabe landet sie auf Kanal 1 - darum steht sie da")


# ====================================================================
# 5. Und der echte Spieler tut es auch
#
# Die Rechnung oben zeigt, dass die Teile zusammenpassen - nicht, dass
# der Soundcheck sie auch so benutzt. Genau das war eine Luecke: Die
# Zeile, die den Kanal aus dem Dateinamen liest, liess sich entfernen,
# ohne dass ein Versuch fiel.
# ====================================================================

import tempfile  # noqa: E402
import types  # noqa: E402

fake_alsaaudio = types.ModuleType("alsaaudio")
for name in (
    "PCM_FORMAT_S16_LE", "PCM_FORMAT_S24_LE", "PCM_FORMAT_S32_LE",
    "PCM_CAPTURE", "PCM_PLAYBACK", "PCM_NORMAL",
):
    setattr(fake_alsaaudio, name, 0)
sys.modules["alsaaudio"] = fake_alsaaudio

from audio.models import AudioDevice  # noqa: E402
from player.player import Player  # noqa: E402


class Ausgang:
    """Merkt sich, womit das Geraet geoeffnet wurde."""

    def __init__(self):
        self.geoeffnet = []
        self.opened = False

    def open(self, device, channels, rate, start_channel=0,
             sample_format=None):
        self.geoeffnet.append((channels, rate, start_channel))
        self.opened = True
        return True

    def write(self, data):
        pass

    def close(self):
        self.opened = False


class Leser:
    """Ein Leser, der nichts liefert - die Wiedergabe endet sofort."""

    channels = 4
    sample_rate = 48000
    duration = 1.0

    def open(self, pfad):
        pass

    def read(self, groesse):
        return None

    def close(self):
        pass


geraet = AudioDevice(
    card=0, device=0, name="X18/XR18", channels=18, sample_rate=48000,
)

with tempfile.TemporaryDirectory() as ordner:

    for name, erwarteter_kanal in (
        ("Probe-1_s9.w64", 8),
        ("Probe-2_s.w64", 0),
        ("Alt-3.w64", 0),
        ("Probe-4_s17.w64", 16),
    ):

        datei = Path(ordner) / name
        datei.write_bytes(b"nicht wirklich w64")

        ausgang = Ausgang()

        spieler = Player(ausgang)
        spieler.reader = Leser()

        assert spieler.start(geraet, datei), f"{name}: nicht gestartet"

        #
        # Der Lesethread laeuft kurz und beendet sich selbst.
        #
        spieler.stop()

        assert ausgang.geoeffnet, f"{name}: Gerät nicht geöffnet"

        kanaele, rate, start = ausgang.geoeffnet[0]

        assert start == erwarteter_kanal, (
            f"{name}: Der Soundcheck spielt ab Kanal {start + 1} statt "
            f"ab Kanal {erwarteter_kanal + 1}. Der Ton käme aus den "
            f"falschen Wegen des Pults, ohne dass es eine Meldung gäbe."
        )

        assert kanaele == 4 and rate == 48000, (kanaele, rate)

print("OK: Der Soundcheck öffnet das Gerät auf den Kanälen der Aufnahme")


# ====================================================================
# 6. Der Recorder gibt den Kanal an den Dateinamen weiter
#
# Auch diese Uebergabe liess sich entfernen, ohne dass etwas fiel -
# und ohne sie steht im Namen nichts, die Aufnahme landete beim
# Soundcheck wieder auf Kanal 1.
# ====================================================================

from recorder.recorder import Recorder  # noqa: E402


class Eingang:
    """Ein Interface, das ein Fenster liefert."""

    def __init__(self, start_channel=8, channels=4):
        self.opened = True
        self.channels = channels
        self.native_channels = INTERFACE
        self.rate = 48000
        self.start_channel = start_channel

    def read(self):
        import time
        time.sleep(0.01)
        return bytes(self.channels * BYTES * 32)

    def aufnahmebreite(self, daten):
        return daten


class Namensmerker:
    """Merkt sich, womit die Datei geoeffnet wurde."""

    def __init__(self):
        self.filename = None
        self.directory = Path(".")
        self.aufrufe = []

    def open(self, channels, sample_rate, bits_per_sample,
             name_prefix="Soundcheck", start_channel=1,
             trenner="-"):
        self.aufrufe.append(start_channel)
        self.filename = f"{name_prefix}-1_s{start_channel}.w64"

    def write(self, daten):
        pass

    def close(self):
        pass


for fenster_start, erwartet in ((8, 9), (0, 1), (16, 17)):

    aufnehmer = Recorder(Eingang(start_channel=fenster_start))
    aufnehmer.writer = Namensmerker()

    assert aufnehmer.start("Probe") is True

    aufnehmer.stop()

    assert aufnehmer.writer.aufrufe == [erwartet], (
        f"Fenster ab Kanal {fenster_start + 1}: Der Schreiber bekam "
        f"{aufnehmer.writer.aufrufe} statt [{erwartet}] - im Dateinamen "
        f"stünde dann der falsche Kanal, und der Soundcheck spielte "
        f"woanders."
    )

print("OK: Der Recorder reicht den ersten Kanal an den Dateinamen durch")


print("Alle Tests zum Aufnahmefenster erfolgreich.")
