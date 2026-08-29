"""
Prüft die neue Recorder-Logik: Pegelprüfung (Monitoring) und
Aufnahme teilen sich denselben Thread, ohne dass ALSA/echte
Hardware nötig ist.
"""

import sys
import time
import types
from pathlib import Path

#
# alsaaudio ist auf diesem Rechner nicht installiert (nur auf dem
# Pi). Recorder importiert darüber nur AudioBackend, das hier gar
# nicht benutzt wird (FakeBackend ersetzt es) - ein Fake-Modul
# genügt, damit der Import klappt.
#
fake_alsaaudio = types.ModuleType("alsaaudio")
fake_alsaaudio.PCM_FORMAT_S24_LE = 1
fake_alsaaudio.PCM_FORMAT_S32_LE = 2
fake_alsaaudio.PCM_CAPTURE = 0
fake_alsaaudio.PCM_PLAYBACK = 1
fake_alsaaudio.PCM_NORMAL = 0
sys.modules["alsaaudio"] = fake_alsaaudio

from recorder.recorder import Recorder


class FakeBackend:
    """Liefert endlos stille Blöcke."""

    def __init__(self, channels=2, rate=48000):
        self.channels = channels
        self.rate = rate
        self._chunk = bytes(channels * 4 * 32)

    def read(self):
        time.sleep(0.005)
        return self._chunk


class FakeWriter:
    """Ersetzt den echten W64Writer - schreibt nirgendwohin."""

    def __init__(self):
        self.filename = None
        self.opened = False
        self.write_count = 0
        self.close_count = 0
        self.directory = Path(".")

    def open(self, channels, sample_rate, bits_per_sample, name_prefix="Soundcheck"):
        self.filename = "fake.w64"
        self.opened = True

    def write(self, data):
        self.write_count += 1

    def close(self):
        self.opened = False
        self.close_count += 1


# ----------------------------------------------------------------
# 1. Reine Pegelprüfung, ohne dass geschrieben wird
# ----------------------------------------------------------------

recorder = Recorder(FakeBackend(channels=4))
recorder.writer = FakeWriter()

assert recorder.start_monitoring() is True
time.sleep(0.05)

assert recorder.monitoring is True
assert recorder.recording is False
assert recorder.writer.opened is False, "Beim reinen Pegeltest darf keine Datei geöffnet werden."
assert len(recorder.levels) == 4, "Pegel-Liste muss zur Kanalzahl passen."
print("OK: Pegelprüfung läuft, ohne aufzuzeichnen")

# Doppeltes Starten soll fehlschlagen
assert recorder.start_monitoring() is False
print("OK: Pegelprüfung kann nicht doppelt gestartet werden")

recorder.stop_monitoring()
assert recorder.monitoring is False
assert recorder.writer.close_count == 0, "stop_monitoring() darf die (nie geöffnete) Datei nicht schließen."
print("OK: Pegelprüfung stoppt sauber, ohne die Datei anzufassen")

# ----------------------------------------------------------------
# 2. Pegelprüfung -> nahtloser Übergang in echte Aufnahme
# ----------------------------------------------------------------

recorder = Recorder(FakeBackend(channels=2))
recorder.writer = FakeWriter()

assert recorder.start_monitoring() is True
time.sleep(0.02)
thread_during_monitoring = recorder._thread

assert recorder.start() is True, "Aufnahme sollte während laufender Pegelprüfung startbar sein."
assert recorder.recording is True
assert recorder.writer.opened is True
assert recorder._thread is thread_during_monitoring, (
    "Der Aufnahme-Thread sollte beim Wechsel von Pegelprüfung zu "
    "Aufnahme NICHT neu gestartet werden."
)
print("OK: Übergang von Pegelprüfung zu Aufnahme ohne Thread-Neustart")

time.sleep(0.05)
assert recorder.writer.write_count > 0, "Es sollte in die Datei geschrieben worden sein."

recorder.stop()
assert recorder.recording is False
assert recorder.monitoring is False
assert recorder.writer.close_count == 1
print("OK: stop() beendet Aufnahme UND Pegelprüfung, Datei wird geschlossen")

# ----------------------------------------------------------------
# 3. Aufnahme direkt starten (ohne vorherige Pegelprüfung)
# ----------------------------------------------------------------

recorder = Recorder(FakeBackend(channels=8))
recorder.writer = FakeWriter()

assert recorder.start() is True
assert recorder.recording is True
assert recorder.monitoring is True
assert len(recorder.levels) == 8
time.sleep(0.03)
assert recorder.writer.write_count > 0

recorder.stop()
assert recorder.writer.close_count == 1
print("OK: Direktes Starten der Aufnahme funktioniert weiterhin wie zuvor")

# ----------------------------------------------------------------
# 4. stop_monitoring() waehrend einer echten Aufnahme ist ein No-Op
# ----------------------------------------------------------------

recorder = Recorder(FakeBackend(channels=2))
recorder.writer = FakeWriter()

recorder.start()
recorder.stop_monitoring()  # sollte NICHT die Aufnahme abwuergen
assert recorder.recording is True, "stop_monitoring() darf eine laufende Aufnahme nicht beenden."
recorder.stop()
print("OK: stop_monitoring() waehrend einer Aufnahme ist wirkungslos (stop() ist dafuer zustaendig)")

# ----------------------------------------------------------------
# 5. Die Lichtsteuerung als dritter Interessent am selben Strom
#
# ALSA erlaubt nur einen Leser. Die musikgesteuerte Lichtshow muss
# aber mithoeren, auch wenn niemand aufnimmt oder Pegel prueft.
# Deshalb merkt sich der Recorder, WER ihn braucht, statt nur "laeuft
# ja/nein".
# ----------------------------------------------------------------

recorder = Recorder(FakeBackend(channels=2))
recorder.writer = FakeWriter()

recorder.start_analysis()
time.sleep(0.02)

assert recorder.stream_active is True, "Das Licht muss den Strom oeffnen koennen."

#
# Aber es prueft niemand Pegel - die Oberflaeche darf das nicht
# behaupten.
#
assert recorder.monitoring is False, (
    "Wenn nur das Licht mithoert, laeuft keine Pegelpruefung."
)

print("OK: Das Licht haelt den Strom offen, ohne als Pegelpruefung zu gelten")

#
# Und die Pegelpruefung muss trotzdem startbar sein. Eine Pruefung
# auf "Thread laeuft" haette hier False geliefert - der Knopf im
# Webinterface haette einfach nichts getan.
#
assert recorder.start_monitoring() is True, (
    "Bei laufender Lichtshow muss sich die Pegelpruefung starten lassen."
)
assert recorder.monitoring is True

recorder.stop_monitoring()

assert recorder.monitoring is False
assert recorder.stream_active is True, (
    "Das Beenden der Pegelpruefung darf die Lichtshow nicht abwuergen."
)

print("OK: Pegelprüfung lässt sich neben der Lichtshow starten und beenden")

#
# Aufnahme dazu, dann Stop: Die Aufnahme endet, das Licht hoert
# weiter mit.
#
assert recorder.start() is True
time.sleep(0.03)
assert recorder.recording is True

recorder.stop()

assert recorder.recording is False
assert recorder.writer.close_count == 1
assert recorder.stream_active is True, (
    "Stop der Aufnahme darf die Lichtshow nicht mitnehmen."
)

print("OK: Stop der Aufnahme lässt die Lichtshow weiterlaufen")

#
# Meldet sich das Licht ab und will sonst niemand etwas, ist Schluss.
#
recorder.stop_analysis()

assert recorder.stream_active is False, (
    "Ohne Interessenten muss der Thread wirklich aufhoeren."
)
assert recorder._thread is None

print("OK: Geht der letzte Interessent, hört der Thread auf")


# ----------------------------------------------------------------
# 6. Mithoerer bekommen die Bloecke - und koennen nichts kaputtmachen
# ----------------------------------------------------------------

recorder = Recorder(FakeBackend(channels=2))
recorder.writer = FakeWriter()

gesehen = []

recorder.add_consumer(lambda block: gesehen.append(len(block)))
recorder.start_analysis()

time.sleep(0.05)

assert len(gesehen) > 0, "Der Mithoerer hat keine Bloecke bekommen."

print("OK: Ein Mithörer bekommt die gelesenen Blöcke")

#
# Und jetzt der Fall, der zaehlt: Ein Mithoerer wirft. Die Aufnahme
# darf davon nichts merken - eine kaputte Lichtshow mitten in einem
# Konzert waere sonst eine abgebrochene Aufnahme.
#
def kaputt(block):
    raise RuntimeError("absichtlich kaputt")

recorder.add_consumer(kaputt)

recorder.start()

vorher = recorder.writer.write_count

time.sleep(0.05)

assert recorder.recording is True, (
    "Ein werfender Mithoerer hat die Aufnahme beendet."
)
assert recorder.writer.write_count > vorher, (
    "Nach dem Fehler eines Mithoerers wurde nicht weitergeschrieben."
)
assert kaputt not in recorder._verbraucher, (
    "Ein werfender Mithoerer muss abgemeldet werden, sonst wirft er ewig weiter."
)

recorder.stop()
recorder.stop_analysis()

print("OK: Ein werfender Mithörer wird abgemeldet, die Aufnahme läuft weiter")


print("Alle Tests erfolgreich.")
