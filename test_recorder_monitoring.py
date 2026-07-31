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

    def open(self, channels, sample_rate, bits_per_sample):
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

print("Alle Tests erfolgreich.")
