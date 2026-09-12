#!/usr/bin/env python3
"""
Prüft die Laufzeitmessung (core/laufzeit_messung.py).

Was hier geprüft wird, ist der Kern der Sache: Ein Mitschnitt mit
BEKANNTER Laufzeit wird künstlich erzeugt, und die Messung muss genau
diese Laufzeit herausbekommen. Damit ist die Rechnung geprüft, ohne
dass ein Pult im Raum steht - und wenn sie am Gerät eine falsche Zahl
liefert, liegt es am Weg und nicht an der Auswertung.

Der Weg selbst (Interface, USB, Pult) lässt sich hier nicht
nachstellen. Genau deshalb gibt es die Messung ja.
"""

import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import core.laufzeit_messung as messung  # noqa: E402
from core.laufzeit_messung import (  # noqa: E402
    KLICK_BEI_S,
    KLICK_DAUER_S,
    KLICK_PEGEL,
    VOLLAUSSCHLAG,
    klick_datei,
    klick_finden,
    versatz_ms,
)
from reader.w64_reader import W64Reader  # noqa: E402
from writer.w64_writer import W64Writer  # noqa: E402

RATE = 48000


def mitschnitt(ordner: Path, versatz_rahmen: int, kanaele: int = 2,
               rauschen: int = 0, mit_klick: bool = True,
               dauer_s: float = 3.0) -> Path:
    """
    Ein Mitschnitt, wie ihn der Recorder schriebe - mit einem Klick an
    einer genau bekannten Stelle.

    `versatz_rahmen` ist die Laufzeit, die herauskommen muss.
    """

    schreiber = W64Writer()
    schreiber.directory = ordner

    schreiber.open(
        channels=kanaele,
        sample_rate=RATE,
        bits_per_sample=24,
        name_prefix="Pruefmitschnitt",
    )

    klick_von = int(KLICK_BEI_S * RATE) + versatz_rahmen
    klick_bis = klick_von + int(KLICK_DAUER_S * RATE)

    block = bytearray()

    for n in range(int(dauer_s * RATE)):

        if mit_klick and klick_von <= n < klick_bis:
            anteil = (n - klick_von) / max(1, klick_bis - klick_von)
            wert = int(
                KLICK_PEGEL * (VOLLAUSSCHLAG - 1) * (1.0 - anteil)
            )
        else:
            #
            # Grundrauschen als saegender Wechsel - ein fester Wert
            # waere eine Gleichspannung und kein Rauschen.
            #
            wert = rauschen if n % 2 else -rauschen

        block += struct.pack("<i", wert) * kanaele

    schreiber.write(bytes(block))
    schreiber.close()

    return Path(schreiber.filename)


arbeit = tempfile.TemporaryDirectory()
ORDNER = Path(arbeit.name)


# ====================================================================
# 1. Der Klick-Mix ist eine echte Datei mit einem Klick darin
#
# Er wird vom selben Schreiber angelegt wie jede Aufnahme - und muss
# vom eigenen Leser wieder zu lesen sein. Eine Messdatei, die XRack
# selbst nicht lesen kann, wäre der denkbar schlechteste Anfang.
# ====================================================================

KANAELE = 18

klick = klick_datei(ORDNER, KANAELE, RATE)

leser = W64Reader()
leser.open(klick)

assert leser.channels == KANAELE, leser.channels
assert leser.sample_rate == RATE, leser.sample_rate

assert abs(leser.duration - messung.MESSDAUER_S) < 0.01, (
    f"Der Klick-Mix ist {leser.duration:.2f} s lang statt "
    f"{messung.MESSDAUER_S} s."
)

leser.close()

#
# Und der Klick sitzt dort, wo er sitzen soll: Auf sich selbst
# angewandt muss die Messung 0 ergeben.
#
rahmen, schwelle = klick_finden(klick)

assert rahmen >= 0, "Im eigenen Klick-Mix ist kein Klick zu finden."

assert abs(rahmen - int(KLICK_BEI_S * RATE)) <= 2, (
    f"Der Klick steht bei Rahmen {rahmen}, erwartet war "
    f"{int(KLICK_BEI_S * RATE)}."
)

gemessen, grund = versatz_ms(klick, RATE)

assert gemessen == 0, (
    f"Der Klick-Mix gegen sich selbst ergibt {gemessen} ms statt 0 - "
    f"dann ist die Rechnung schon im Ansatz verschoben. ({grund})"
)

print("OK: Der Klick-Mix ist lesbar und der Klick sitzt an seiner Stelle")


# ====================================================================
# 2. Eine bekannte Laufzeit wird genau wiedergefunden
#
# Das ist die Messung. Alles andere ist Beiwerk.
# ====================================================================

for erwartet_ms in (0, 12, 21, 43, 85, 170, 500):

    rahmen = int(erwartet_ms * RATE / 1000)

    datei = mitschnitt(ORDNER, rahmen)

    gemessen, grund = versatz_ms(datei, RATE)

    assert grund == "", grund

    assert abs(gemessen - erwartet_ms) <= 1, (
        f"Bei einer Laufzeit von {erwartet_ms} ms misst XRack "
        f"{gemessen} ms. Der Mitschnitt läge beim Zusammenhören um die "
        f"Differenz daneben."
    )

print("OK: Bekannte Laufzeiten von 0 bis 500 ms werden genau gemessen")


# ====================================================================
# 3. Grundrauschen auf dem Kanal stört nicht
#
# Am Pult liegt auf dem aufgenommenen Kanal selten absolute Stille -
# ein Mikrofon rauscht, ein Verstärker brummt. Die Schwelle richtet
# sich deshalb nach dem gemessenen Grundrauschen und nicht nach einer
# festen Zahl.
# ====================================================================

laut = mitschnitt(ORDNER, int(0.06 * RATE), rauschen=int(0.01 * VOLLAUSSCHLAG))

gemessen, grund = versatz_ms(laut, RATE)

assert grund == "", grund

assert abs(gemessen - 60) <= 1, (
    f"Mit Grundrauschen misst XRack {gemessen} ms statt 60 - das "
    f"Rauschen wurde für den Klick gehalten."
)

print("OK: Grundrauschen auf dem Kanal wird nicht für den Klick gehalten")


# ====================================================================
# 4. Kein Klick ist ein Befund, kein Messwert
#
# Wenn der Weg im Pult nicht geschlossen ist, kommt nichts zurück.
# Dann eine Zahl auszugeben wäre das Schlimmste, was die Messung tun
# könnte: Sie würde stillschweigend falsch korrigieren.
# ====================================================================

still = mitschnitt(ORDNER, 0, mit_klick=False,
                   rauschen=int(0.002 * VOLLAUSSCHLAG))

gemessen, grund = versatz_ms(still, RATE)

assert gemessen < 0, (
    f"Aus einem Mitschnitt ohne Klick kam die Zahl {gemessen} heraus."
)

assert "Pult" in grund and "zurück" in grund, (
    f"Die Begründung sagt nicht, was zu tun ist: {grund!r}"
)

print("OK: Ohne Klick gibt es eine Begründung statt einer Zahl")


# ====================================================================
# 5. Ein zu kurzer Mitschnitt liefert keine erfundene Zahl
#
# Ist die Laufzeit grösser als der Rest des Mitschnitts, steht der
# Klick gar nicht darin.
# ====================================================================

kurz = mitschnitt(ORDNER, int(0.05 * RATE), dauer_s=0.5)

gemessen, grund = versatz_ms(kurz, RATE)

assert gemessen < 0 and grund, (
    f"Aus einem zu kurzen Mitschnitt kam {gemessen} ms heraus."
)

print("OK: Ein zu kurzer Mitschnitt liefert keine erfundene Zahl")


# ====================================================================
# 6. Die erste Flanke zählt, nicht die lauteste Stelle
#
# Durch das Pult kommt der Klick nicht allein zurück: Nachhall,
# Rückkopplung, ein Kompressor, der erst nachregelt. Was danach kommt,
# kann lauter sein als der Anfang - gesucht ist aber der Anfang, denn
# er ist die Laufzeit.
# ====================================================================

schreiber = W64Writer()
schreiber.directory = ORDNER
schreiber.open(channels=2, sample_rate=RATE, bits_per_sample=24,
               name_prefix="Nachhall")

erste = int(KLICK_BEI_S * RATE) + int(0.04 * RATE)
zweite = erste + int(0.15 * RATE)

block = bytearray()

for n in range(int(3.0 * RATE)):

    if erste <= n < erste + 240:
        wert = int(0.2 * VOLLAUSSCHLAG)
    elif zweite <= n < zweite + 240:
        #
        # Deutlich lauter - und trotzdem nicht der gesuchte Anfang.
        #
        wert = int(0.9 * VOLLAUSSCHLAG)
    else:
        wert = 0

    block += struct.pack("<i", wert) * 2

schreiber.write(bytes(block))
schreiber.close()

gemessen, grund = versatz_ms(Path(schreiber.filename), RATE)

assert abs(gemessen - 40) <= 1, (
    f"Gemessen wurden {gemessen} ms statt 40 - gefunden wurde die "
    f"lauteste Stelle statt der ersten. Die Laufzeit wäre damit um "
    f"den Nachhall zu gross."
)

print("OK: Gemessen wird die erste Flanke, nicht die lauteste Stelle")


# ====================================================================
# 7. Der ganze Ablauf - mit einem Pult, das den Klick zurückschickt
#
# Bis hierher war es die Rechnung. Jetzt der Weg, den XRack am Gerät
# geht: Klick-Mix schreiben, abspielen, dabei aufnehmen, auswerten,
# Wert merken, aufräumen.
#
# Nachgestellt ist nur die Hardware - und zwar so, wie sie sich wirklich
# verhält: Das "Pult" schickt zurück, was es bekommt, aber um eine
# bekannte Laufzeit verzögert. Genau diese Laufzeit muss am Ende
# dastehen.
# ====================================================================

import threading  # noqa: E402
import time  # noqa: E402
import types  # noqa: E402

fake_alsaaudio = types.ModuleType("alsaaudio")
for name in (
    "PCM_FORMAT_S16_LE", "PCM_FORMAT_S24_LE", "PCM_FORMAT_S32_LE",
    "PCM_CAPTURE", "PCM_PLAYBACK", "PCM_NORMAL",
):
    setattr(fake_alsaaudio, name, 0)
sys.modules.setdefault("alsaaudio", fake_alsaaudio)

from core.application.musik import MusikMixin  # noqa: E402
from core.state_store import StateStore  # noqa: E402

LAUFZEIT_MS = 75


class Pult:
    """
    Ein Pult, das zurückschickt, was es bekommt - um LAUFZEIT_MS
    verzögert.

    Das ist die ganze Nachstellung. Was XRack ausgibt, landet in einer
    Warteschlange; was XRack aufnimmt, kommt um die Laufzeit versetzt
    wieder heraus.
    """

    def __init__(self, kanaele_aus, kanaele_ein, rate):
        self.kanaele_aus = kanaele_aus
        self.kanaele_ein = kanaele_ein
        self.rate = rate
        self.ausgegeben = bytearray()
        self.gelesen_rahmen = 0
        self.schloss = threading.Lock()

    def ausgeben(self, daten):
        with self.schloss:
            self.ausgegeben += daten

    def aufnehmen(self, rahmen):
        """
        Liefert `rahmen` Rahmen der Aufnahme - das, was vor
        LAUFZEIT_MS ausgegeben wurde.
        """

        verzug = int(LAUFZEIT_MS * self.rate / 1000)

        block = bytearray()

        with self.schloss:

            for n in range(self.gelesen_rahmen,
                           self.gelesen_rahmen + rahmen):

                quelle = n - verzug

                wert = 0

                if quelle >= 0:
                    stelle = quelle * self.kanaele_aus * 4
                    if stelle + 4 <= len(self.ausgegeben):
                        wert = struct.unpack(
                            "<i", bytes(self.ausgegeben[stelle:stelle + 4])
                        )[0]

                block += struct.pack("<i", wert) * self.kanaele_ein

            self.gelesen_rahmen += rahmen

        return bytes(block)


class Ausgang:
    """Der Wiedergabeweg - er reicht alles ans Pult weiter."""

    def __init__(self, pult):
        self.pult = pult
        self.opened = False

    def open(self, device, channels, rate, start_channel=0,
             sample_format=None):
        #
        # Ein echtes ALSA-Geraet braucht zum Oeffnen Zeit, und zwar
        # jedes Mal unterschiedlich viel. Hier steht die Zeit fest -
        # sie ist dafuer da, dass es auffaellt, wenn die Aufnahme vor
        # dem ersten Block startet: Dann maesse man diese Anlaufzeit
        # mit, und die Messung waere um sie zu gross.
        #
        time.sleep(0.12)
        self.opened = True
        return True

    def write(self, daten):
        #
        # Bremsen wie ein echtes Interface: Ohne das waere der
        # Klick-Mix in Millisekunden durch, und der Recorder haette
        # nichts zu lesen.
        #
        time.sleep(0.004)
        self.pult.ausgeben(daten)

    def close(self):
        self.opened = False


class Eingang:
    """Der Aufnahmeweg - er holt sich, was das Pult zurückschickt."""

    RAHMEN = 1024

    def __init__(self, pult, kanaele, rate):
        self.pult = pult
        self.opened = True
        self.channels = kanaele
        self.native_channels = kanaele
        self.rate = rate
        self.start_channel = 0

    def read(self):
        time.sleep(0.004)
        return self.pult.aufnehmen(self.RAHMEN)

    def aufnahmebreite(self, daten):
        return daten


class Geraet:
    id = "hw:1,0"
    channels = 2
    name = "Pruefpult"


class Anwendung(MusikMixin):
    """Die echten Methoden auf nachgestellter Hardware."""

    def __init__(self, ordner, spieler, aufnehmer):

        self.logger = logging.getLogger("XRack")

        self.state_store = StateStore(ordner / "state.json")

        self.music_player = spieler
        self.recorder = aufnehmer
        self.player = types.SimpleNamespace(playing=False)

        self.selected_audio_device = Geraet()
        self.mixer_sample_rate = RATE
        self.record_name_prefix = "Soundcheck"

        self.player_mode = "practice"
        self.practice_repeat = False
        self.practice_record = False
        self.practice_recording = False
        self.practice_active = False
        self.practice_offset_ms = 0

        self._laufzeit_lock = threading.Lock()
        self._laufzeit_stand = {
            "active": False, "success": None, "ms": 0, "error": "",
        }


import logging  # noqa: E402

from player.music_library import MusicLibrary  # noqa: E402
from player.music_player import MusicPlayer  # noqa: E402
from recorder.recorder import Recorder  # noqa: E402

lauf_ordner = tempfile.TemporaryDirectory()
LAUF = Path(lauf_ordner.name)

pult = Pult(kanaele_aus=Geraet.channels, kanaele_ein=Geraet.channels,
            rate=RATE)

spieler = MusicPlayer(Ausgang(pult), MusicLibrary(LAUF))

aufnehmer = Recorder(Eingang(pult, Geraet.channels, RATE))
aufnehmer.writer.directory = LAUF

anwendung = Anwendung(LAUF, spieler, aufnehmer)

#
# Die Messdatei ist drei Sekunden lang - der Lauf dauert also
# mindestens so lange. Kuerzer geht es nicht: Gemessen wird eine
# Laufzeit, und die braucht Zeit.
#
erfolg, meldung = anwendung.start_laufzeit_messung()

assert erfolg, meldung

frist = time.monotonic() + 90

while anwendung.laufzeit_status()["active"] and time.monotonic() < frist:
    time.sleep(0.1)

stand = anwendung.laufzeit_status()

assert stand["success"] is True, (
    f"Die Messung kam zu keinem Ergebnis: {stand}"
)

assert abs(stand["ms"] - LAUFZEIT_MS) <= 30, (
    f"Gemessen wurden {stand['ms']} ms, das Pult verzögert um "
    f"{LAUFZEIT_MS} ms. (Die Toleranz ist grosszügig: Die "
    f"nachgestellten Puffer laufen nicht taktgenau - es geht darum, "
    f"dass die richtige Grössenordnung herauskommt und nicht Null.)"
)

assert anwendung.practice_offset_ms == stand["ms"], (
    "Der gemessene Wert wurde nicht als Versatz übernommen - dann "
    "hätte die Messung nichts bewirkt."
)

assert StateStore(LAUF / "state.json").get(
    "practice_offset_ms"
) == stand["ms"], "Der gemessene Wert wurde nicht am Gerät gemerkt."

print(f"OK: Der ganze Ablauf misst die Laufzeit ({stand['ms']} ms)")


# ====================================================================
# 8. Die Messung räumt hinter sich auf
#
# Klick-Mix und Mitschnitt sind Wegwerfdateien. Blieben sie liegen,
# stünden sie in der Aufnahmenliste, und niemand wüsste, wozu.
# ====================================================================

geblieben = sorted(p.name for p in LAUF.glob("*.w64"))

assert geblieben == [], (
    f"Nach der Messung liegen noch Dateien herum: {geblieben}"
)

assert aufnehmer.recording is False, "Die Aufnahme läuft noch."

assert spieler.playing is False, "Die Wiedergabe läuft noch."

print("OK: Die Messung räumt Klick und Mitschnitt wieder weg")


# ====================================================================
# 9. Zwei Messungen gleichzeitig gibt es nicht
# ====================================================================

with anwendung._laufzeit_lock:
    anwendung._laufzeit_stand["active"] = True

erfolg, meldung = anwendung.start_laufzeit_messung()

assert not erfolg and meldung, "Eine zweite Messung wurde angenommen."

with anwendung._laufzeit_lock:
    anwendung._laufzeit_stand["active"] = False

#
# Und nicht gegen eine laufende Wiedergabe: Die Messung ist selbst
# eine - zwei gleichzeitig kann das Interface nicht.
#
anwendung.practice_active = True
anwendung.music_player._playing = True

erfolg, meldung = anwendung.start_laufzeit_messung()

assert not erfolg and meldung, (
    "Die Messung startete gegen eine laufende Wiedergabe."
)

anwendung.practice_active = False
anwendung.music_player._playing = False

print("OK: Die Messung startet nicht gegen etwas Laufendes")


lauf_ordner.cleanup()

arbeit.cleanup()

print("Alle Tests der Laufzeitmessung erfolgreich.")
