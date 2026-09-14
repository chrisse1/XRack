#!/usr/bin/env python3
"""
Prüft, dass sich der eigene Versuch zum Übungsmix dazuhören lässt.

Das Interface gibt nur EINEN Wiedergabestrom her - zwei Wiedergaben
gleichzeitig kann es nicht. Nichts hindert XRack aber daran, in diesen
einen Strom ZWEI Dateien zu legen: den Übungsmix auf seine Kanäle, den
Mitschnitt auf seine (siehe player/ueben_decoder.py).

Geprüft wird mit ECHTEN Dateien, die XRacks eigener Schreiber anlegt -
jeder Kanal mit seinem eigenen Wert. Eine Verschiebung um einen
einzigen Kanal fällt damit sofort auf, und genau das ist der Fehler,
der hier möglich ist: Der Versuch läge dann auf der Spur eines anderen
Instruments, und am Pult klänge es, als sei der Mix kaputt.
"""

#
# Der Suchpfad zur Projektwurzel - siehe tests/_wurzel.py. Muss VOR
# allen Importen aus XRack stehen.
#
from _wurzel import WURZEL  # noqa: F401,E402


import struct
import sys
import tempfile
import time
import types
from pathlib import Path


fake_alsaaudio = types.ModuleType("alsaaudio")
for name in (
    "PCM_FORMAT_S16_LE", "PCM_FORMAT_S24_LE", "PCM_FORMAT_S32_LE",
    "PCM_CAPTURE", "PCM_PLAYBACK", "PCM_NORMAL",
):
    setattr(fake_alsaaudio, name, 0)
sys.modules.setdefault("alsaaudio", fake_alsaaudio)

from audio.models import AudioDevice  # noqa: E402
from core.recording_kind import (  # noqa: E402
    MARKER_PRACTICE,
    MARKER_SOUNDCHECK,
)
from player.music_library import MusicLibrary  # noqa: E402
from player.music_player import MusicPlayer  # noqa: E402
from player.ueben_decoder import UebenDecoder  # noqa: E402
from writer.w64_writer import W64Writer  # noqa: E402

RATE = 48000
INTERFACE = 18
BYTES = 4


def w64(ordner: Path, kanaele: int, rahmen: int, wert_ab: int,
        marker: str, praefix: str, start_channel: int = 1) -> Path:
    """
    Eine echte Datei, wie XRack sie schreibt.

    Kanal k trägt konstant `wert_ab + k` - damit lässt sich zu jedem
    Wert sagen, aus welcher Datei und aus welchem Kanal er stammt.
    """

    schreiber = W64Writer()
    schreiber.directory = ordner

    schreiber.open(
        channels=kanaele,
        sample_rate=RATE,
        bits_per_sample=24,
        name_prefix=praefix,
        marker=marker,
        start_channel=start_channel,
    )

    block = bytearray()

    for _ in range(rahmen):
        for kanal in range(kanaele):
            block += struct.pack("<i", wert_ab + kanal)

    schreiber.write(bytes(block))
    schreiber.close()

    return Path(schreiber.filename)


def kanalwerte(daten: bytes, kanaele: int, rahmen: int = 0) -> list[int]:
    """Die Werte eines einzelnen Rahmens."""

    anfang = rahmen * kanaele * BYTES

    return [
        struct.unpack(
            "<i", daten[anfang + k * BYTES:anfang + (k + 1) * BYTES]
        )[0]
        for k in range(kanaele)
    ]


arbeit = tempfile.TemporaryDirectory()
ORDNER = Path(arbeit.name)

#
# Der Mix: acht Kanaele ab Kanal 1, Werte 1000001..1000008.
# Der Versuch: zwei Kanaele ab Kanal 9, Werte 2000001..2000002.
#
MIX = w64(ORDNER, 8, RATE, 1000001, MARKER_PRACTICE, "Pruefmix")
TAKE = w64(ORDNER, 2, RATE, 2000001, MARKER_SOUNDCHECK, "Versuch",
           start_channel=9)

CHUNK = 256 * INTERFACE * BYTES


# ====================================================================
# 1. Beide Dateien landen auf ihren eigenen Kanälen
#
# Der Kern der Sache. Ein Versuch, der auf den Kanälen des Mixes
# landet, ist schlimmer als keiner: Man hört einen Brei und sucht den
# Fehler am Pult.
# ====================================================================

dekoder = UebenDecoder()

dekoder.einrichten(
    breite=INTERFACE,
    start_channel=0,
    mitschnitt=TAKE,
    mitschnitt_start=8,
)

assert dekoder.passt(MIX), (
    "Mix und Versuch passen angeblich nicht auf 18 Kanäle - acht ab 1 "
    "und zwei ab 9 sind aber zusammen zehn."
)

assert dekoder.open(MIX, channels=INTERFACE, rate=RATE), (
    "Die Quellen liessen sich nicht öffnen."
)

block = dekoder.read(CHUNK)

assert block, "Es kam kein Block."

werte = kanalwerte(block, INTERFACE)

assert werte[:8] == [1000001 + k for k in range(8)], (
    f"Auf den Kanälen 1-8 steht {werte[:8]} - dort gehört der "
    f"Übungsmix hin, unverschoben."
)

assert werte[8:10] == [2000001, 2000002], (
    f"Auf den Kanälen 9-10 steht {werte[8:10]} - dort gehört der "
    f"Versuch hin. Ein Kanal daneben, und er liegt auf einer fremden "
    f"Spur."
)

assert werte[10:] == [0] * 8, (
    f"Die Kanäle 11-18 sind nicht still: {werte[10:]}"
)

#
# Und der zehnte Rahmen genauso - ein Fehler in der Schrittweite
# zeigt sich erst nach dem ersten.
#
spaeter = kanalwerte(block, INTERFACE, rahmen=10)

assert spaeter == werte, (
    f"Rahmen 10 sieht anders aus als Rahmen 0:\n  {spaeter}\n  {werte}"
)

dekoder.close()

print("OK: Mix und Versuch liegen auf ihren eigenen Kanälen")


# ====================================================================
# 2. Der Mix gibt die Länge vor
#
# Ein kürzerer Versuch wird ab seinem Ende still, ein längerer endet
# mit dem Mix: Man übt zum Stück, nicht umgekehrt.
# ====================================================================

KURZ = w64(ORDNER, 2, 300, 2000001, MARKER_SOUNDCHECK, "Kurz",
           start_channel=9)

dekoder.einrichten(
    breite=INTERFACE,
    start_channel=0,
    mitschnitt=KURZ,
    mitschnitt_start=8,
)

assert dekoder.open(MIX, channels=INTERFACE, rate=RATE)

erster = dekoder.read(256 * INTERFACE * BYTES)

assert kanalwerte(erster, INTERFACE)[8:10] == [2000001, 2000002], (
    "Der kurze Versuch fehlt schon im ersten Block."
)

#
# Ab Rahmen 300 ist der Versuch zu Ende - der Mix laeuft weiter.
#
zweiter = dekoder.read(256 * INTERFACE * BYTES)

ende = kanalwerte(zweiter, INTERFACE, rahmen=100)

assert ende[:8] == [1000001 + k for k in range(8)], (
    f"Nach dem Ende des Versuchs fehlt auch der Mix: {ende[:8]}"
)

assert ende[8:10] == [0, 0], (
    f"Nach seinem Ende steht auf den Kanälen des Versuchs {ende[8:10]} "
    f"statt Stille - dort wiederholte sich der letzte Block."
)

dekoder.close()

#
# Umgekehrt: Der laengere Versuch endet mit dem Mix.
#
MINI = w64(ORDNER, 8, 200, 1000001, MARKER_PRACTICE, "Minimix")

dekoder.einrichten(
    breite=INTERFACE,
    start_channel=0,
    mitschnitt=TAKE,
    mitschnitt_start=8,
)

assert dekoder.open(MINI, channels=INTERFACE, rate=RATE)

gelesen = 0

while True:

    block = dekoder.read(CHUNK)

    if block is None:
        break

    gelesen += len(block) // (INTERFACE * BYTES)

    assert gelesen <= 200, (
        f"Der Strom läuft mit {gelesen} Rahmen über den Mix (200) "
        f"hinaus - das wäre ein Nachspiel aus einem Versuch, das "
        f"niemand hören will."
    )

assert gelesen == 200, f"Gelesen wurden {gelesen} von 200 Rahmen."

dekoder.close()

print("OK: Der Mix gibt die Länge vor, in beide Richtungen")


# ====================================================================
# 3. Ein Sprung bewegt beide Quellen
#
# Sonst liefe der Versuch nach jedem Spulen gegen einen anderen Teil
# des Stücks - und das Üben wäre wertlos.
# ====================================================================

#
# Eine Datei, deren Werte mit dem Rahmen wachsen: Daran laesst sich
# ablesen, WO gelesen wird.
#
schreiber = W64Writer()
schreiber.directory = ORDNER
schreiber.open(
    channels=2, sample_rate=RATE, bits_per_sample=24,
    name_prefix="Zaehler", marker=MARKER_SOUNDCHECK, start_channel=9,
)
block = bytearray()
for n in range(RATE):
    block += struct.pack("<i", n) + struct.pack("<i", n)
schreiber.write(bytes(block))
schreiber.close()

ZAEHLER = Path(schreiber.filename)

dekoder.einrichten(
    breite=INTERFACE,
    start_channel=0,
    mitschnitt=ZAEHLER,
    mitschnitt_start=8,
)

assert dekoder.open(
    MIX, channels=INTERFACE, rate=RATE, start_position=0.5
)

gesprungen = kanalwerte(dekoder.read(CHUNK), INTERFACE)

assert gesprungen[:8] == [1000001 + k for k in range(8)], (
    "Nach dem Sprung fehlt der Mix."
)

erwartet = RATE // 2

assert abs(gesprungen[8] - erwartet) <= 1, (
    f"Der Versuch steht nach dem Sprung bei Rahmen {gesprungen[8]} "
    f"statt bei {erwartet} - er liefe gegen eine andere Stelle des "
    f"Stücks."
)

dekoder.close()

print("OK: Ein Sprung bewegt Mix und Versuch gemeinsam")


# ====================================================================
# 4. Was über den Rand ragt, wird vorher abgelehnt
#
# Nicht unterwegs abgeschnitten: Ein halbes Stereopaar ist kein
# Stereo, und in den nächsten Rahmen zu schreiben hiesse, dass ab dort
# ALLES verschoben ist.
# ====================================================================

dekoder.einrichten(
    breite=INTERFACE,
    start_channel=0,
    mitschnitt=TAKE,
    mitschnitt_start=17,
)

assert not dekoder.passt(MIX), (
    "Ein Versuch, der auf Kanal 18+19 läge, wurde angenommen - das "
    "Interface hat 18 Kanäle."
)

dekoder.einrichten(breite=INTERFACE, start_channel=12, mitschnitt=None)

assert not dekoder.passt(MIX), (
    "Ein Acht-Kanal-Mix ab Kanal 13 wurde angenommen - er bräuchte "
    "bis Kanal 20."
)

dekoder.einrichten(breite=INTERFACE, start_channel=10, mitschnitt=None)

assert dekoder.passt(MIX), (
    "Ein Acht-Kanal-Mix ab Kanal 11 passt bis Kanal 18 - er wurde "
    "trotzdem abgelehnt."
)

print("OK: Was nicht auf das Interface passt, wird vorher abgelehnt")


# ====================================================================
# 5. Durch den echten Spieler
#
# Bis hierher war es der Dekoder allein. Jetzt derselbe Weg wie am
# Gerät: play_practice() mit Mitschnitt - das Interface muss mit
# seiner vollen Kanalzahl geöffnet werden, und was herauskommt, muss
# auf den richtigen Kanälen liegen.
# ====================================================================

class Ausgang:
    """
    Ein Interface, das sich Zeit lässt.

    Das Bremsen ist wichtig: Ein echtes ALSA-Gerät nimmt die Blöcke im
    Takt der Samplerate an. Ein Ausgang, der alles sofort schluckt,
    spielt eine Sekunde Material in Millisekunden ab - der Titel wäre
    vorbei, bevor der Versuch hinsieht.
    """

    def __init__(self, takt=0.004):
        self.geoeffnet = []
        self.opened = False
        self.bloecke = []
        self.takt = takt

    def open(self, device, channels, rate, start_channel=0,
             sample_format=None):
        self.geoeffnet.append((channels, rate, start_channel))
        self.opened = True
        return True

    def write(self, daten):
        time.sleep(self.takt)
        self.bloecke.append(daten)

    def close(self):
        self.opened = False


def warte_auf(bedingung, frist=5.0, was=""):
    """Wartet, bis etwas WIRKLICH eingetreten ist - nie fest."""

    ende = time.monotonic() + frist

    while time.monotonic() < ende:

        if bedingung():
            return True

        time.sleep(0.01)

    raise AssertionError(f"Nach {frist} s nicht eingetreten: {was}")


geraet = AudioDevice(
    card=0, device=0, name="X18/XR18", channels=INTERFACE,
    sample_rate=RATE,
)

ausgang = Ausgang()

spieler = MusicPlayer(ausgang, MusicLibrary(ORDNER))

assert spieler.play_practice(
    geraet, MIX, start_channel=0, rate=RATE,
    mitschnitt=TAKE, mitschnitt_start=8,
), "Üben mit Mitschnitt liess sich nicht starten."

warte_auf(lambda: ausgang.bloecke, was="der erste Block")

kanaele, rate, start = ausgang.geoeffnet[0]

assert (kanaele, start) == (INTERFACE, 0), (
    f"Der Spieler öffnet das Interface mit {kanaele} Kanälen ab {start} "
    f"- mit zwei Quellen legt der Dekoder sie selbst an ihren Platz, "
    f"und das Interface wird mit voller Breite geöffnet."
)

werte = kanalwerte(ausgang.bloecke[0], INTERFACE)

spieler.stop()

assert werte[:8] == [1000001 + k for k in range(8)], werte[:8]

assert werte[8:10] == [2000001, 2000002], (
    f"Durch den Spieler landet der Versuch auf {werte[8:10]} statt auf "
    f"seinen eigenen Kanälen."
)

print("OK: Der Spieler legt beide Quellen in einen Strom")


# ====================================================================
# 6. Ohne Mitschnitt bleibt alles beim Alten
#
# Der Gegenfall zählt: Ein Weg, der immer über den neuen Dekoder
# liefe, würde die geprüfte Wiedergabe von Stufe 2 ersetzen, ohne
# dass es jemandem auffällt.
# ====================================================================

ausgang = Ausgang()

spieler = MusicPlayer(ausgang, MusicLibrary(ORDNER))

assert spieler.play_practice(geraet, MIX, start_channel=0, rate=RATE)

warte_auf(lambda: ausgang.bloecke, was="der erste Block ohne Mitschnitt")

kanaele, rate, start = ausgang.geoeffnet[0]

spieler.stop()

assert kanaele == 8, (
    f"Ohne Mitschnitt öffnet der Spieler {kanaele} Kanäle - ein "
    f"Übungsmix bringt seine acht selbst mit, und das Einsetzen macht "
    f"das Backend."
)

print("OK: Ohne Mitschnitt läuft der Weg von Stufe 2 unverändert")


# ====================================================================
# 7. Der Versatz zieht NUR den Mitschnitt vor
#
# Der Mitschnitt hinkt dem Mix immer hinterher, um die Laufzeit des
# ganzen Weges: XRack schreibt in den ALSA-Puffer, das Pult wandelt,
# mischt und schickt zurück, XRack liest wieder aus einem Puffer.
# Ausrechnen lässt sich das von hier aus nicht - anwenden schon: Steht
# der Mix an Stelle p, wird der Mitschnitt ab p+versatz gelesen.
#
# Geprüft mit einer Datei, deren Werte mit dem Rahmen wachsen - daran
# lässt sich ablesen, WO gelesen wird.
# ====================================================================

schreiber = W64Writer()
schreiber.directory = ORDNER
schreiber.open(
    channels=2, sample_rate=RATE, bits_per_sample=24,
    name_prefix="Zaehler2", marker=MARKER_SOUNDCHECK, start_channel=9,
)
block = bytearray()
for n in range(RATE):
    block += struct.pack("<i", n) + struct.pack("<i", n)
schreiber.write(bytes(block))
schreiber.close()

ZAEHLER2 = Path(schreiber.filename)

VERSATZ = 0.25

#
# Auch der MIX muss mitzaehlen, sonst faellt eine Verschiebung an ihm
# gar nicht auf: Die Pruefdatei von oben traegt in jedem Rahmen
# dieselben Werte, ein Sprung darin ist unsichtbar. Genau daran ist
# die erste Fassung dieses Abschnitts vorbeigelaufen.
#
schreiber = W64Writer()
schreiber.directory = ORDNER
schreiber.open(
    channels=8, sample_rate=RATE, bits_per_sample=24,
    name_prefix="Zaehlmix", marker=MARKER_PRACTICE,
)
block = bytearray()
for n in range(RATE):
    block += struct.pack("<i", n)
    for kanal in range(1, 8):
        block += struct.pack("<i", 1000001 + kanal)
schreiber.write(bytes(block))
schreiber.close()

ZAEHLMIX = Path(schreiber.filename)

dekoder = UebenDecoder()

dekoder.einrichten(
    breite=INTERFACE,
    start_channel=0,
    mitschnitt=ZAEHLER2,
    mitschnitt_start=8,
    versatz=VERSATZ,
)

assert dekoder.open(ZAEHLMIX, channels=INTERFACE, rate=RATE)

werte = kanalwerte(dekoder.read(CHUNK), INTERFACE)

dekoder.close()

assert werte[0] == 0, (
    f"Der Mix beginnt bei Rahmen {werte[0]} statt bei 0 - der Versatz "
    f"hat ihn mitverschoben. Dann verschiebt sich alles gemeinsam, und "
    f"gewonnen ist nichts."
)

erwartet = int(VERSATZ * RATE)

assert abs(werte[8] - erwartet) <= 1, (
    f"Der Mitschnitt steht bei Rahmen {werte[8]} statt bei {erwartet} - "
    f"um {VERSATZ * 1000:.0f} ms vorgezogen zu werden, muss er dort "
    f"anfangen."
)

#
# Und zusammen mit einem Sprung: Beides addiert sich, sonst stimmte
# die Zuordnung nach jedem Spulen nicht mehr.
#
dekoder.einrichten(
    breite=INTERFACE,
    start_channel=0,
    mitschnitt=ZAEHLER2,
    mitschnitt_start=8,
    versatz=VERSATZ,
)

assert dekoder.open(
    ZAEHLMIX, channels=INTERFACE, rate=RATE, start_position=0.5
)

gesprungen = kanalwerte(dekoder.read(CHUNK), INTERFACE)

dekoder.close()

assert abs(gesprungen[0] - int(0.5 * RATE)) <= 1, (
    f"Nach dem Sprung steht der Mix bei {gesprungen[0]} statt bei "
    f"{int(0.5 * RATE)} - der Versatz gehört nicht auf ihn."
)

erwartet = int((0.5 + VERSATZ) * RATE)

assert abs(gesprungen[8] - erwartet) <= 1, (
    f"Nach dem Sprung steht der Mitschnitt bei {gesprungen[8]} statt "
    f"bei {erwartet} - Sprung und Versatz müssen sich addieren."
)

print("OK: Der Versatz zieht nur den Mitschnitt vor, auch nach Sprüngen")


# ====================================================================
# 8. Ein negativer Versatz gibt es nicht
#
# Der Mitschnitt kann dem Mix nicht vorauseilen - das wäre Hellsehen.
# Ein negativer Wert wäre ein Denkfehler und soll nicht
# stillschweigend etwas Falsches tun.
# ====================================================================

dekoder.einrichten(
    breite=INTERFACE,
    start_channel=0,
    mitschnitt=ZAEHLER2,
    mitschnitt_start=8,
    versatz=-0.25,
)

#
# Gemessen an einer Sprungstelle, nicht bei 0: Am Anfang faengt der
# Sprung "nach hinten" ohnehin am Dateianfang an, ein negativer Wert
# sieht dort aus wie keiner. Erst mitten im Stueck zeigt sich, ob er
# wirkt - und dort waere er ein hoerbarer Fehler.
#
assert dekoder.open(
    ZAEHLMIX, channels=INTERFACE, rate=RATE, start_position=0.5
)

zurueck = kanalwerte(dekoder.read(CHUNK), INTERFACE)

dekoder.close()

erwartet = int(0.5 * RATE)

assert abs(zurueck[8] - erwartet) <= 1, (
    f"Bei negativem Versatz steht der Mitschnitt bei {zurueck[8]} "
    f"statt bei {erwartet} - er würde dem Mix vorauseilen, und das "
    f"wäre Hellsehen."
)

print("OK: Ein negativer Versatz bleibt wirkungslos")


# ====================================================================
# 9. Die Aufnahme beginnt mit dem ersten Block, nicht vorher
#
# Das ist die Voraussetzung dafür, dass der Versatz überhaupt eine
# feste Grösse ist. Zwischen "Aufnahme starten" und "der erste Ton
# geht hinaus" liegen das Öffnen von ALSA, ein Threadstart und das
# Öffnen der Datei - zusammen einige zehn Millisekunden, und jedes Mal
# unterschiedlich viele. Dieser Zufall stünde sonst im Mitschnitt und
# liesse sich durch nichts mehr herausrechnen.
# ====================================================================

class LangsamerAusgang(Ausgang):
    """Ein Interface, dessen Öffnen dauert - wie in echt."""

    def open(self, device, channels, rate, start_channel=0,
             sample_format=None):
        time.sleep(0.05)
        return super().open(device, channels, rate, start_channel,
                            sample_format)


ausgang = LangsamerAusgang()

spieler = MusicPlayer(ausgang, MusicLibrary(ORDNER))

gerufen = []

spieler.play_practice(
    geraet, MIX, start_channel=0, rate=RATE,
    beim_start=lambda: gerufen.append(len(ausgang.bloecke)),
)

warte_auf(lambda: len(ausgang.bloecke) > 3, was="mehrere Blöcke")

spieler.stop()

assert gerufen == [1], (
    f"Der Ruf kam nach {gerufen} Blöcken (erwartet: genau einmal, nach "
    f"dem ersten). Vorher hiesse: Die Aufnahme läuft, bevor ein Ton da "
    f"ist - und um wie viel, weiss hinterher niemand."
)

print("OK: Der Ruf für die Aufnahme kommt genau mit dem ersten Block")


arbeit.cleanup()

print("Alle Tests zum Mitschnitt beim Üben erfolgreich.")
