#!/usr/bin/env python3
"""
Prüft zwei Wächter, die eine Aufnahme retten können.

**Die Samplerate.** XRack kann sie nicht erkennen - Mischpulte der
X-Serie melden über USB immer den ganzen unterstützten Bereich, nicht
ihre laufende Clock. Steht die Einstellung falsch, läuft trotzdem
alles: Pegel, Aufnahme, Lichtshow. Auffallen tut es beim Abhören,
wenn die Aufnahme zu schnell oder zu langsam ist - und dann ist der
Abend vorbei. Messen lässt es sich aber, denn die Blöcke kommen im
Takt der tatsächlichen Clock.

**Der Speicherplatz.** Am X32 schreibt XRack rund 22 GB je Stunde
(32 Kanäle, 4 Byte, 48 kHz). Läuft die Karte mitten in einer Aufnahme
voll, bricht das Schreiben ab, und der Dateikopf bekommt seine
Größen nicht mehr nachgetragen - unlesbar statt kurz. Deshalb wird
vorher aufgehört.

Gemessen wird mit gestellten Zeiten, nicht mit echter Uhr: Eine
zeitabhängige Zusicherung wäre wacklig, und geprüft werden soll die
Rechnung, nicht die Geschwindigkeit dieses Rechners.
"""

import sys
import time
import types
from pathlib import Path

#
# alsaaudio gibt es nur auf dem Pi. Recorder importiert darüber nur
# AudioBackend, das hier durch eine Attrappe ersetzt wird.
#
fake_alsaaudio = types.ModuleType("alsaaudio")
fake_alsaaudio.PCM_FORMAT_S16_LE = 0
fake_alsaaudio.PCM_FORMAT_S24_LE = 1
fake_alsaaudio.PCM_FORMAT_S32_LE = 2
fake_alsaaudio.PCM_FORMAT_S24_3LE = 3
fake_alsaaudio.PCM_CAPTURE = 0
fake_alsaaudio.PCM_PLAYBACK = 1
fake_alsaaudio.PCM_NORMAL = 0
sys.modules["alsaaudio"] = fake_alsaaudio

sys.path.insert(0, str(Path(__file__).resolve().parent))

from recorder.rate_check import (  # noqa: E402
    BYTES_JE_WERT,
    MINDESTZEIT_S,
    RateCheck,
)

from recorder.recorder import Recorder  # noqa: E402


def bloecke(pruefung: RateCheck, kanaele: int, rate_echt: float,
            dauer: float, rahmen_je_block: int = 1024) -> None:
    """
    Füttert die Prüfung so, wie ein Interface mit `rate_echt` Hz
    liefern würde - mit gestellter Uhr.
    """

    schritt = rahmen_je_block / rate_echt
    laenge = rahmen_je_block * kanaele * BYTES_JE_WERT

    jetzt = 1000.0

    #
    # Der erste Block setzt nur die Uhr (siehe RateCheck.block).
    #
    pruefung.block(laenge, jetzt)

    while jetzt < 1000.0 + dauer:
        jetzt += schritt
        pruefung.block(laenge, jetzt)


# ====================================================================
# 1. Stimmt die Rate, sagt niemand etwas
# ====================================================================

pruefung = RateCheck(channels=18, erwartet=48000)

bloecke(pruefung, kanaele=18, rate_echt=48000, dauer=10.0)

assert pruefung.stimmt() is True, pruefung.status()
assert abs(pruefung.gemessen - 48000) < 100, pruefung.status()
assert pruefung.vermutet == 48000, pruefung.status()

print(f"OK: 48 kHz eingestellt, 48 kHz gelesen - stimmig "
      f"({pruefung.gemessen:.0f} Hz)")


# ====================================================================
# 2. Der Fall, um den es geht: 44,1 gelesen, 48 eingestellt
#
# Acht Prozent daneben. Die Aufnahme wäre hinterher zu langsam - und
# genau das soll XRack sagen, bevor der Abend vorbei ist.
# ====================================================================

pruefung = RateCheck(channels=18, erwartet=48000)

bloecke(pruefung, kanaele=18, rate_echt=44100, dauer=10.0)

assert pruefung.stimmt() is False, pruefung.status()

assert pruefung.vermutet == 44100, (
    f"Die Meldung soll die vermutete Rate nennen: {pruefung.status()}"
)

print(f"OK: 48 kHz eingestellt, 44,1 gelesen - fällt auf "
      f"(vermutet {pruefung.vermutet} Hz)")


#
# Und andersherum genauso.
#
pruefung = RateCheck(channels=32, erwartet=44100)

bloecke(pruefung, kanaele=32, rate_echt=48000, dauer=10.0)

assert pruefung.stimmt() is False, pruefung.status()
assert pruefung.vermutet == 48000, pruefung.status()

print("OK: Auch der umgekehrte Irrtum fällt auf")


#
# Und der dritte Fall, der leicht untergeht: Die Messung passt zu
# GAR KEINER üblichen Rate. Dann ist die Einstellung nicht falsch,
# sondern es gehen Rahmen verloren - Aussetzer beim Lesen. XRack darf
# dann keine Rate raten.
#
pruefung = RateCheck(channels=32, erwartet=48000)

bloecke(pruefung, kanaele=32, rate_echt=46000, dauer=10.0)

assert pruefung.stimmt() is False, pruefung.status()

assert pruefung.vermutet == 0, (
    "Zu einer Messung, die zu keiner üblichen Rate passt, darf keine "
    f"geraten werden: {pruefung.status()}"
)

print("OK: Passt die Messung zu keiner üblichen Rate, wird nicht geraten")


# ====================================================================
# 3. Solange zu wenig gemessen wurde, gibt es KEIN Urteil
#
# Das ist der wichtige Fall. Ein "stimmt nicht" nach einer halben
# Sekunde wäre schlimmer als gar nichts: Man würde eine richtige
# Einstellung ändern.
# ====================================================================

pruefung = RateCheck(channels=18, erwartet=48000)

bloecke(pruefung, kanaele=18, rate_echt=44100, dauer=MINDESTZEIT_S / 2)

assert pruefung.stimmt() is None, (
    f"Nach {MINDESTZEIT_S / 2} s darf es noch kein Urteil geben: "
    f"{pruefung.status()}"
)
assert pruefung.gemessen == 0.0, pruefung.status()
assert pruefung.status()["plausible"] is None

#
# Ganz ohne Daten erst recht nicht.
#
leer = RateCheck(channels=18, erwartet=48000)

assert leer.stimmt() is None
assert leer.gemessen == 0.0

print(f"OK: Unter {MINDESTZEIT_S:.0f} Sekunden gibt es kein Urteil")


# ====================================================================
# 4. Der erste Block zählt nicht mit
#
# In ihm steckt der Rückstau aus dem ALSA-Puffer, der sich seit dem
# Öffnen angesammelt hat. Zählte er mit, wäre die gemessene Rate
# gerade am Anfang zu hoch - also dort, wo noch nichts mittelt.
# ====================================================================

pruefung = RateCheck(channels=2, erwartet=48000)

#
# Ein dicker Rückstau: eine halbe Sekunde Audio auf einen Schlag.
#
pruefung.block(24000 * 2 * BYTES_JE_WERT, 1000.0)

#
# Danach sauber im Takt.
#
jetzt = 1000.0

for _ in range(int(48000 / 1024 * 10)):
    jetzt += 1024 / 48000
    pruefung.block(1024 * 2 * BYTES_JE_WERT, jetzt)

assert pruefung.stimmt() is True, (
    f"Der Rückstau des ersten Blocks verfälscht die Messung: "
    f"{pruefung.status()}"
)

print("OK: Der Rückstau im ersten Block verfälscht nichts")


# ====================================================================
# 5. Der Recorder misst wirklich mit
#
# Bis hierher war es reine Rechnung. Jetzt der echte Lesethread mit
# einem Backend, das in bekanntem Takt liefert - mit großzügiger
# Toleranz, weil dort die Uhr dieses Rechners mitspielt.
# ====================================================================


class TaktBackend:
    """Liefert Blöcke im Takt einer vorgegebenen Samplerate."""

    RAHMEN = 512

    #
    # Wie das echte Backend: Ein Strom ist offen (siehe
    # Recorder.bereit).
    #
    opened = True

    def __init__(self, channels=2, rate=48000, echte_rate=None):

        self.channels = channels
        self.native_channels = channels
        self.rate = rate

        self._echt = echte_rate or rate
        self._chunk = bytes(channels * BYTES_JE_WERT * self.RAHMEN)

    def read(self):
        time.sleep(self.RAHMEN / self._echt)
        return self._chunk

    def aufnahmebreite(self, data):
        return data


class StillerWriter:

    def __init__(self):
        self.filename = None
        self.directory = Path(".")
        self.write_count = 0
        self.closed = 0

    def open(self, channels, sample_rate, bits_per_sample,
             name_prefix="", start_channel=1,
             trenner="-"):
        self.start_channel = start_channel
        self.filename = "fake.w64"

    def write(self, data):
        self.write_count += 1

    def close(self):
        self.closed += 1


recorder = Recorder(TaktBackend(channels=2, rate=48000, echte_rate=44100))
recorder.writer = StillerWriter()

recorder.start_analysis()

time.sleep(MINDESTZEIT_S + 1.0)

stand = recorder.rate_check.status()

recorder.stop_analysis()

assert stand["plausible"] is False, (
    f"Der Recorder merkt die falsche Rate nicht: {stand}"
)

assert 0.85 < stand["measured"] / 44100 < 1.15, (
    f"Die Messung liegt zu weit daneben: {stand}"
)

print(f"OK: Der Recorder misst mit ({stand['measured']:.0f} Hz statt "
      f"{stand['expected']})")


# ====================================================================
# 6. Der Speicherplatz: Restzeit, Warnung, sauberer Stopp
# ====================================================================

import shutil  # noqa: E402

import recorder.recorder as recorder_modul  # noqa: E402


class PlatzBackend(TaktBackend):
    """Schnell liefernd - der Test soll nicht in Echtzeit laufen."""

    def read(self):
        time.sleep(0.002)
        return self._chunk


def platz_stellen(frei: int):
    """Den freien Platz vorgeben, ohne die Karte vollzuschreiben."""

    class Belegung:
        total = 1 << 40
        used = 0

    Belegung.free = frei

    recorder_modul.shutil = types.SimpleNamespace(
        disk_usage=lambda pfad: Belegung
    )


#
# Erst die Rechnung: 32 Kanäle bei 48 kHz sind 6,1 MB je Sekunde,
# also rund 22 GB je Stunde. Bei 220 GB frei muss die Restzeit etwa
# zehn Stunden betragen.
#
proband = Recorder(PlatzBackend(channels=32, rate=48000))
proband.writer = StillerWriter()

platz_stellen(220 * 1000 ** 3)

rate = proband.datenrate()

assert rate == 32 * 4 * 48000, rate

stunden = proband.platz_restzeit() / 3600

assert 9.5 < stunden < 10.5, (
    f"Die Restzeit passt nicht zur Datenrate: {stunden:.2f} h"
)

print(f"OK: 32 Kanäle bei 48 kHz sind {rate / 1000 ** 3 * 3600:.1f} GB/h "
      f"- Restzeit {stunden:.1f} h")


#
# Reicht es schon vor dem Start nicht mehr, wird gar nicht erst
# angefangen: Eine Datei, die im selben Atemzug wieder geschlossen
# wird, hilft niemandem.
#
platz_stellen(int(rate * 10))

assert proband.start() is False, (
    "Bei fast vollem Speicher darf keine Aufnahme beginnen."
)
assert proband.writer.filename is None, "Es wurde trotzdem eine Datei angelegt."

print("OK: Bei fast vollem Speicher beginnt gar keine Aufnahme")


#
# Und der Fall, der zählt: Der Platz geht WÄHREND der Aufnahme aus.
# Sie muss dann BEENDET werden, nicht abbrechen - die Datei ist
# danach geschlossen.
#
platz_stellen(220 * 1000 ** 3)

proband = Recorder(PlatzBackend(channels=32, rate=48000))
proband.writer = StillerWriter()

assert proband.start() is True

time.sleep(0.3)

assert proband.writer.write_count > 0, (
    "Es wurde gar nichts geschrieben - dann prüft der Versuch nichts."
)

geschrieben = proband.writer.write_count

#
# Jetzt wird es eng.
#
platz_stellen(int(rate * 10))

zeit = time.monotonic()

while proband.recording and time.monotonic() - zeit < 5.0:
    time.sleep(0.05)

assert not proband.recording, (
    "Die Aufnahme läuft weiter, obwohl der Platz fast weg ist."
)

assert proband.platz_stopp is True, "Der Grund wurde nicht gemerkt."

assert proband.writer.closed >= 1, (
    "Die Datei wurde nicht geschlossen - der Dateikopf bekommt seine "
    "Größen dann nie, und die Aufnahme ist unlesbar."
)

assert proband.writer.write_count >= geschrieben, (
    "Nach der Bremse fehlen Blöcke, die vorher schon geschrieben waren."
)

#
# Aufgeräumt wird im Hauptfaden (der Lesethread darf sich nicht
# selbst anhalten - er würde auf sich selbst warten).
#
assert proband.platz_aufraeumen() is True

assert proband._thread is None, "Der Lesethread läuft weiter."

print("OK: Bei knappem Platz wird die Aufnahme beendet, nicht abgebrochen")


#
# Mit reichlich Platz passiert nichts dergleichen.
#
platz_stellen(220 * 1000 ** 3)

satt = Recorder(PlatzBackend(channels=32, rate=48000))
satt.writer = StillerWriter()

satt.start()

time.sleep(0.3)

assert satt.recording is True, "Bei reichlich Platz darf nichts bremsen."
assert satt.platz_stopp is False

satt.stop()

print("OK: Bei reichlich Platz läuft die Aufnahme durch")


# ====================================================================
# 7. Die Aufnahmebreite folgt dem Interface - aber nur ungefragt
#
# Am X32 gemeldet: XRack nimmt 18 von 32 Kanaelen auf. Die 18 sind
# die Vorgabe vom XR18, und beim Geraetewechsel wurde bisher nur nach
# UNTEN begrenzt - nach oben nie. Wer die Zahl dagegen selbst gesetzt
# hat, will sie behalten.
# ====================================================================

from core.application.audio import AudioMixin  # noqa: E402
from core.application.aufnahme import AufnahmeMixin  # noqa: E402


class Geraet:
    """So viel AudioDevice, wie select_audio_device anfasst."""

    def __init__(self, kanaele):
        self.id = f"hw:{kanaele}"
        self.channels = kanaele
        self.name = "Testgerät"
        self.description = "Testgerät"
        self.sample_rate = 48000
        self.sample_bits = 24
        self.formats = ["S24_LE"]


class Speicher:
    """Zustandsspeicher im Arbeitsspeicher."""

    def __init__(self):
        self.werte = {}

    def get(self, schluessel, vorgabe=None):
        return self.werte.get(schluessel, vorgabe)

    def set(self, schluessel, wert):
        self.werte[schluessel] = wert


class AudioApp(AudioMixin, AufnahmeMixin):
    """Nur die Teile von Application, die an der Kanalzahl hängen."""

    def __init__(self, gemerkt=18):

        import logging

        self.logger = logging.getLogger("XRack-Test")
        self.state_store = Speicher()

        self.record_channels = gemerkt

        #
        # Der erste aufgenommene Kanal - aufgenommen wird ein Fenster,
        # nicht immer der Anfang (siehe test_aufnahmefenster.py).
        #
        self.record_start_channel = 1

        self.selected_audio_device = None

        self.geraete = {}

        #
        # audio_core und recorder werden beim Umstellen angefasst -
        # hier genuegen Attrappen, die nichts tun.
        #
        self.audio_core = type(
            "Kern",
            (),
            {
                "opened": False,
                "max_channels": 32,
                "close": lambda selbst: None,
                "open": lambda selbst, *args, **kwargs: True,
            },
        )()

        self.audio_manager = self

    #
    # mixer_sample_rate ist in AudioMixin eine Eigenschaft, die aus
    # der Konfiguration liest - hier genuegt ein fester Wert.
    #
    @property
    def mixer_sample_rate(self):
        return 48000

    #
    # Statt AudioManager: Geraete nach Kennung.
    #
    def get_device(self, kennung):
        return self.geraete.get(kennung)

    def scan(self, skip_probe_id=None):
        pass


def app_mit(geraet_kanaele: int, gemerkt: int = 18) -> AudioApp:

    app = AudioApp(gemerkt=gemerkt)

    geraet = Geraet(geraet_kanaele)
    app.geraete[geraet.id] = geraet

    return app


#
# Nie von Hand gewaehlt: Das X32 bringt 32 Kanaele mit, also werden
# 32 aufgenommen.
#
app = app_mit(32)

assert app.select_audio_device("hw:32") is True

assert app.record_channels == 32, (
    "Ein Interface mit 32 Kanälen muss auch 32 Aufnahmekanäle ergeben, "
    f"gefunden: {app.record_channels}"
)

print("OK: Ohne eigene Wahl gilt die volle Breite des Interfaces")


#
# Von Hand gewaehlt: Die Wahl bleibt stehen.
#
app = app_mit(32)

app.set_record_channels(8, manuell=True)

assert app.select_audio_device("hw:32") is True

assert app.record_channels == 8, (
    "Eine Wahl von Hand darf beim Gerätewechsel nicht überschrieben "
    f"werden, gefunden: {app.record_channels}"
)

print("OK: Eine Wahl von Hand bleibt stehen")


#
# Und das Begrenzen nach unten bleibt: Ein kleines Interface kann
# nicht mehr liefern, als es hat.
#
app = app_mit(8, gemerkt=18)

app.set_record_channels(18, manuell=True)

assert app.select_audio_device("hw:8") is True

assert app.record_channels == 8, (
    f"Mehr Kanäle als das Interface hat: {app.record_channels}"
)

print("OK: Mehr als das Interface hergibt, wird weiterhin gekappt")


print("Alle Raten- und Speicherplatz-Tests erfolgreich.")
