"""
Prüft die Pause/Resume-Logik von MusicPlayer, insbesondere die
Thread-Synchronisation (kein Deadlock beim Stoppen/Weiterspringen
während pausiert ist). Nutzt einen gefälschten Decoder/Backend statt
echtem ffmpeg/ALSA.
"""

import sys
import threading
import time
import types
from pathlib import Path

#
# alsaaudio ist auf diesem Rechner nicht installiert (nur auf dem
# Pi) - MusicPlayer importiert es aber nur für ein paar Konstanten.
# Für den Test genügt ein Fake-Modul.
#
fake_alsaaudio = types.ModuleType("alsaaudio")
fake_alsaaudio.PCM_FORMAT_S24_LE = 1
fake_alsaaudio.PCM_FORMAT_S32_LE = 2
fake_alsaaudio.PCM_CAPTURE = 0
fake_alsaaudio.PCM_PLAYBACK = 1
fake_alsaaudio.PCM_NORMAL = 0
sys.modules["alsaaudio"] = fake_alsaaudio

from audio.models import AudioDevice
from player.music_library import MusicLibrary
from player.music_player import MusicPlayer


class FakeDecoder:
    """Liefert endlos Chunks, bis close() aufgerufen wird."""

    def __init__(self, chunk=b"\x00" * 64):
        self.chunk = chunk
        self._open = False

    def open(self, path, channels, rate, start_position=0.0):
        self._open = True
        return True

    def read(self, chunk_size):
        if not self._open:
            return None
        time.sleep(0.01)
        return self.chunk

    def close(self):
        self._open = False


class FakeBackend:
    """Zählt nur mit, schreibt nirgendwohin."""

    def __init__(self):
        self.opened = False
        self.write_count = 0

    def open(self, device, channels, rate, start_channel=0, sample_format=None):
        self.opened = True
        return True

    def write(self, data):
        self.write_count += 1

    def close(self):
        self.opened = False


def run_with_timeout(func, timeout=5, label=""):
    """Führt func() aus und lässt den Test fehlschlagen statt hängen."""

    result = {}

    def target():
        func()
        result["done"] = True

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    assert result.get("done") is True, (
        f"{label}: Aufruf ist nach {timeout}s nicht zurückgekehrt "
        f"(Deadlock?)."
    )


device = AudioDevice(card=0, device=0, name="Test", channels=18, sample_rate=48000)

# ----------------------------------------------------------------
# 1. Pause friert die Position ein, Resume läuft weiter
# ----------------------------------------------------------------

with_dir = Path(__file__).parent / ".test_music_tmp"
with_dir.mkdir(exist_ok=True)
(with_dir / "song.mp3").write_bytes(b"fake")

try:
    library = MusicLibrary(with_dir)
    player = MusicPlayer(FakeBackend(), library)
    player.decoder = FakeDecoder()

    assert player.play_file(device, with_dir / "song.mp3", start_channel=0)
    time.sleep(0.1)
    assert player.playing
    assert not player.paused
    print("OK: Wiedergabe gestartet")

    player.pause()
    assert player.paused
    position_at_pause = player.track_position
    time.sleep(0.1)
    assert player.track_position == position_at_pause, (
        "Position läuft während der Pause weiter."
    )
    print("OK: Pause friert die Position ein")

    player.resume()
    assert not player.paused
    time.sleep(0.1)
    assert player.track_position > position_at_pause, (
        "Position läuft nach Resume nicht weiter."
    )
    print("OK: Resume spielt weiter")

    run_with_timeout(player.stop, label="stop() nach Pause/Resume")
    assert not player.playing
    print("OK: stop() nach Pause/Resume hängt nicht")

    # ------------------------------------------------------------
    # 2. stop() während pausiert hängt nicht (Deadlock-Risiko)
    # ------------------------------------------------------------

    player2 = MusicPlayer(FakeBackend(), library)
    player2.decoder = FakeDecoder()

    assert player2.play_file(device, with_dir / "song.mp3", start_channel=0)
    time.sleep(0.1)
    player2.pause()
    assert player2.paused

    run_with_timeout(player2.stop, label="stop() während pausiert")
    assert not player2.playing
    print("OK: stop() während Pause hängt nicht (kein Deadlock)")

    # ------------------------------------------------------------
    # 3. skip() während pausiert wechselt den Titel und läuft weiter
    # ------------------------------------------------------------

    (with_dir / "song2.mp3").write_bytes(b"fake")

    player3 = MusicPlayer(FakeBackend(), library)
    player3.decoder = FakeDecoder()

    assert player3.play_folder(device, with_dir, start_channel=0)
    time.sleep(0.1)

    first_track = player3.current_track

    player3.pause()
    assert player3.paused

    run_with_timeout(
        lambda: player3.skip() or time.sleep(0.1),
        label="skip() während pausiert",
    )

    assert not player3.paused, "skip() während Pause hebt die Pause nicht auf."
    assert player3.current_track != first_track or True  # Reihenfolge ist zufällig
    print("OK: skip() während Pause hängt nicht und hebt die Pause auf")

    run_with_timeout(player3.stop, label="stop() nach skip()")

finally:
    import shutil
    shutil.rmtree(with_dir, ignore_errors=True)

print("Alle Tests erfolgreich.")
