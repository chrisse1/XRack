"""
Prüft, dass AudioBackend/AudioCore beim Öffnen die explizit
übergebene Samplerate verwenden - nicht mehr den (irreführenden, weil
nur den USB-Wertebereich widerspiegelnden) device.sample_rate-Wert.
Regressionstest für "Musikwiedergabe/Aufnahme zu langsam bei 44,1 kHz
statt 48 kHz Mischpult-Samplerate".

Nutzt ein Fake-`alsaaudio`-Modul statt echter Hardware.
"""

import sys
import types

fake_alsaaudio = types.ModuleType("alsaaudio")
fake_alsaaudio.PCM_FORMAT_S24_LE = 1
fake_alsaaudio.PCM_FORMAT_S32_LE = 2
fake_alsaaudio.PCM_CAPTURE = 0
fake_alsaaudio.PCM_PLAYBACK = 1
fake_alsaaudio.PCM_NORMAL = 0


class FakePCM:
    """Nimmt jede angeforderte Rate klaglos an (wie echte USB-Audio-
    Interfaces es laut Recherche typischerweise auch tun)."""

    def __init__(self, type, mode, device):
        self.requested_rate = None

    def setrate(self, rate):
        self.requested_rate = rate
        return rate

    def setchannels(self, channels):
        pass

    def setformat(self, fmt):
        pass

    def setperiodsize(self, size):
        pass

    def close(self):
        pass


fake_alsaaudio.PCM = FakePCM
sys.modules["alsaaudio"] = fake_alsaaudio

from audio.audio_backend import AudioBackend
from audio.audio_core import AudioCore
from audio.models import AudioDevice


# ----------------------------------------------------------------
# 1. AudioBackend.open() verwendet die übergebene Rate, nicht
#    device.sample_rate (der USB-Capability-Wertebereich, z.B.
#    immer 48000 durch _parse_max_value()).
# ----------------------------------------------------------------

device = AudioDevice(card=0, device=0, name="Test-X32", channels=18, sample_rate=48000)

backend = AudioBackend()
assert backend.open(device, channels=18, rate=44100)
assert backend.rate == 44100, (
    "AudioBackend.open() ignoriert die übergebene Rate und verwendet "
    "weiterhin device.sample_rate."
)
print("OK: AudioBackend.open() verwendet die übergebene Rate")

# ----------------------------------------------------------------
# 2. Ohne explizite Rate fällt AudioBackend auf device.sample_rate
#    zurück (Abwärtskompatibilität für Aufrufer, die keine Rate
#    übergeben).
# ----------------------------------------------------------------

backend_fallback = AudioBackend()
assert backend_fallback.open(device, channels=18)
assert backend_fallback.rate == 48000, (
    "Fallback auf device.sample_rate funktioniert nicht mehr."
)
print("OK: Fallback auf device.sample_rate ohne explizite Rate")

# ----------------------------------------------------------------
# 3. AudioCore.sample_rate spiegelt die tatsächlich geöffnete Rate
#    wider, nicht mehr device.sample_rate.
# ----------------------------------------------------------------

core = AudioCore()
assert core.open(device, channels=18, rate=44100)
assert core.sample_rate == 44100, (
    "AudioCore.sample_rate liefert weiterhin den USB-Capability-Wert "
    "statt der tatsächlich geöffneten Rate."
)
print("OK: AudioCore.sample_rate spiegelt die tatsächlich geöffnete Rate")

print("Alle Tests erfolgreich.")
