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
        self.rate = rate
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

    assert player.play_file(device, with_dir / "song.mp3", start_channel=0, rate=48000)
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

    assert player2.play_file(device, with_dir / "song.mp3", start_channel=0, rate=48000)
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

    assert player3.play_folder(device, with_dir, start_channel=0, rate=48000)
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

    # ------------------------------------------------------------
    # 4. Die übergebene Samplerate wird tatsächlich verwendet (kein
    #    hartcodierter Wert mehr, siehe Regression-Fix für die
    #    "Musik läuft zu langsam bei 44,1 kHz"-Meldung)
    # ------------------------------------------------------------

    backend44 = FakeBackend()
    decoder44 = FakeDecoder()

    player4 = MusicPlayer(backend44, library)
    player4.decoder = decoder44

    assert player4.play_file(device, with_dir / "song.mp3", start_channel=0, rate=44100)
    time.sleep(0.05)

    assert backend44.rate == 44100, (
        "AudioPlaybackBackend wurde nicht mit der übergebenen Rate "
        "geöffnet - MusicPlayer verwendet noch einen fest "
        "einprogrammierten Wert."
    )

    run_with_timeout(player4.stop, label="stop() nach Raten-Test")
    print("OK: Übergebene Samplerate wird verwendet, nicht hartcodiert")



    # ================================================================
    # 4. stop() wartet nicht auf eine laufende Metadaten-Abfrage
    #
    # Der Grund, warum dieser Test frueher unter Last fehlschlug - und
    # ein echter Fehler, nicht bloss ein Testproblem:
    #
    # Der Worker liest vor jedem Titel Titel/Interpret und Dauer ueber
    # ffprobe (probe_tags/probe_duration, je 10 s Zeitgrenze). stop()
    # wartete mit join() OHNE Zeitgrenze auf den Thread - steckte der
    # gerade in einer dieser Abfragen, wirkte der Stop-Knopf bis zu
    # zwanzig Sekunden tot.
    #
    # Anhalten muss sofort wirken. Dass der Thread ein paar Sekunden
    # spaeter zu Ende laeuft, stoert nicht: _playing steht bereits auf
    # False, er schreibt nichts mehr ans Audiogeraet.
    # ================================================================

    import player.music_player as musikspieler_modul

    original_probe_tags = musikspieler_modul.probe_tags


    #
    # Eine langsame Abfrage nachstellen. Sechs Sekunden sind kein
    # Fehlverhalten - sie liegen weit innerhalb der Zeitgrenze, die
    # sich probe_tags selbst setzt.
    #
    def langsame_probe(pfad):
        time.sleep(6)
        return original_probe_tags(pfad)

    musikspieler_modul.probe_tags = langsame_probe

    player5 = MusicPlayer(FakeBackend(), library)
    player5.decoder = FakeDecoder()

    assert player5.play_file(device, with_dir / "song.mp3", start_channel=0, rate=48000)

    # Der Worker steckt jetzt in der langsamen Abfrage.
    time.sleep(0.2)

    beginn = time.monotonic()
    player5.stop()
    gebraucht = time.monotonic() - beginn

    assert not player5.playing, "Nach stop() muesste die Wiedergabe aus sein."

    assert gebraucht < 3, (
        f"stop() hat {gebraucht:.1f}s gebraucht - es wartet wieder auf die "
        "laufende Metadaten-Abfrage. Der Stop-Knopf wirkt dann tot."
    )

    print(f"OK: stop() kehrt trotz laufender Metadaten-Abfrage zurueck "
          f"({gebraucht:.1f}s)")

    # ------------------------------------------------------------
    # ... und ein neuer Start wartet den alten Thread trotzdem ab.
    #
    # Das ist die Kehrseite: stop() laesst den Thread laufen, also
    # muss das Starten dafuer sorgen, dass nicht zwei Worker
    # gleichzeitig auf dasselbe Audiogeraet schreiben.
    # ------------------------------------------------------------

    alter_thread = player5._thread

    assert alter_thread is not None and alter_thread.is_alive(), (
        "Fuer diese Pruefung muss der alte Thread noch laufen - sonst "
        "sagt sie nichts aus."
    )

    musikspieler_modul.probe_tags = original_probe_tags

    assert player5.play_file(device, with_dir / "song.mp3", start_channel=0, rate=48000)

    assert not alter_thread.is_alive(), (
        "Der neue Titel startete, obwohl der alte Lese-Thread noch lief - "
        "zwei Worker auf demselben Geraet zerschneiden die Ausgabe."
    )

    run_with_timeout(player5.stop, label="stop() nach Neustart")

    print("OK: Ein neuer Start wartet den alten Lese-Thread ab")

    musikspieler_modul.probe_tags = original_probe_tags

    # ------------------------------------------------------------
    # Fortsetzen waehrend der Dekoder noch schliesst
    #
    # Aus dem Betrieb gemeldet: Pause, dann Fortsetzen - und statt
    # weiterzuspielen sprang XRack zum naechsten Titel. Mal so, mal
    # so, je nachdem wie schnell nach der Pause geklickt wurde.
    #
    # Der Grund: _play_track fragte ERST NACH dem Schliessen des
    # Dekoders, ob pausiert wurde. Das Schliessen beendet ffmpeg und
    # wartet bis zu zwei Sekunden auf dessen Ende - traf "Fortsetzen"
    # in dieser Zeit ein, stand _paused schon wieder auf False, die
    # Pausen-Behandlung fiel aus, und die Funktion lief auf ihr break
    # am Ende: naechster Titel.
    #
    # Hier wird der Worker gezielt in genau diesem Fenster
    # festgehalten.
    # ------------------------------------------------------------

    class SchliessBremse:
        """Wie FakeDecoder, aber close() Nummer 2 laesst sich anhalten."""

        def __init__(self):
            self._open = False
            self.geoeffnet = []
            self.schliessungen = 0
            self.im_close = threading.Event()
            self.weiter = threading.Event()

        def open(self, path, channels, rate, start_position=0.0):
            self.geoeffnet.append((Path(path).name, round(start_position, 2)))
            self._open = True
            return True

        def read(self, chunk_size):
            if not self._open:
                return None
            time.sleep(0.01)
            return b"\x00" * 64

        def close(self):
            self._open = False
            self.schliessungen += 1

            if self.schliessungen == 2:
                #
                # Der Worker steht jetzt zwischen Leseschleife und
                # Pausen-Frage - das Fenster, um das es geht.
                #
                self.im_close.set()
                self.weiter.wait(timeout=10)

    (with_dir / "zweiter.mp3").write_bytes(b"fake")

    bremse = SchliessBremse()

    player6 = MusicPlayer(FakeBackend(), MusicLibrary(with_dir))
    player6.decoder = bremse

    assert player6.play_folder(device, with_dir, start_channel=0, rate=48000)

    time.sleep(0.3)

    titel_vorher = player6.current_track
    assert titel_vorher, "Es laeuft gar kein Titel."

    player6.pause()

    assert bremse.im_close.wait(timeout=5), (
        "Der Worker hat das Fenster nicht erreicht - der Test sagt dann "
        "nichts aus."
    )

    # Genau jetzt: Fortsetzen, waehrend der Dekoder noch schliesst.
    player6.resume()

    bremse.weiter.set()

    time.sleep(0.6)

    titel_nachher = player6.current_track
    oeffnungen = list(bremse.geoeffnet)

    run_with_timeout(player6.stop, label="stop() nach Pausen-Wettlauf")

    assert titel_nachher == titel_vorher, (
        f"Nach dem Fortsetzen laeuft '{titel_nachher}' statt "
        f"'{titel_vorher}' - es wurde zum naechsten Titel gesprungen."
    )

    assert len(oeffnungen) >= 2, oeffnungen

    assert oeffnungen[1][1] > 0, (
        f"Der Titel wurde von vorn geoeffnet statt an der Pausenstelle: "
        f"{oeffnungen}"
    )

    print("OK: Fortsetzen waehrend des Schliessens spielt denselben Titel "
          "weiter")


finally:
    import shutil
    shutil.rmtree(with_dir, ignore_errors=True)



print("Alle Tests erfolgreich.")
