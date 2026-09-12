"""
XRack Player (Soundcheck-Wiedergabe).
"""

import logging
import threading
from pathlib import Path
from time import monotonic

from audio.audio_playback_backend import AudioPlaybackBackend
from audio.models import AudioDevice
from core.recording_kind import start_channel_from_filename
from reader.w64_reader import W64Reader


class Player:
    """
    Spielt eine Wave64-Aufnahme auf denselben Kanälen ab,
    auf denen sie aufgenommen wurde ("virtueller Soundcheck").

    "Denselben Kanälen" ist seit dem Aufnahmefenster mehr als eine
    Redewendung: Wurde ab Kanal 9 aufgenommen, muss die Datei auch
    wieder ab Kanal 9 herauskommen. Woher der Kanal kommt, steht im
    Dateinamen - siehe core/recording_kind.py.
    """

    CHUNK_FRAMES = 1024

    def __init__(
        self,
        backend: AudioPlaybackBackend,
    ):

        self.logger = logging.getLogger("XRack")

        self.backend = backend

        self.reader = W64Reader()

        self._playing = False

        self._thread: threading.Thread | None = None

        self._current_filename = ""

        #
        # Der erste Kanal, auf dem die laufende Datei liegt (0-basiert).
        #
        self._start_channel = 0

        self._start_time = None

        self._last_duration = 0.0

    @property
    def playing(self) -> bool:
        """True während der Wiedergabe."""
        return self._playing

    @property
    def current_filename(self) -> str:
        return self._current_filename

    @property
    def start_channel(self) -> int:
        """Der erste Kanal der laufenden Wiedergabe (0-basiert)."""

        return self._start_channel

    @property
    def channels(self) -> int:
        return self.reader.channels

    @property
    def sample_rate(self) -> int:
        return self.reader.sample_rate

    @property
    def duration(self) -> float:
        """
        Verstrichene Zeit der aktuellen bzw. letzten Wiedergabe.
        """

        if self.playing and self._start_time is not None:
            return monotonic() - self._start_time

        return self._last_duration

    def start(
        self,
        device: AudioDevice,
        path: Path,
    ) -> bool:
        """
        Startet die Wiedergabe einer Datei.
        """

        if self.playing:
            return False

        if not path.exists():
            return False

        self.reader.open(path)

        #
        # Der erste Kanal steht im Namen der Datei. Ohne ihn landete
        # eine Aufnahme der Kanäle 9-12 wieder auf 1-4 - der Ton käme
        # aus den falschen Wegen des Pults, und zwar ohne Fehlermeldung.
        #
        start_channel = start_channel_from_filename(path.name) - 1

        if not self.backend.open(
            device,
            channels=self.reader.channels,
            rate=self.reader.sample_rate,
            start_channel=start_channel,
        ):
            self.reader.close()
            return False

        self._start_channel = start_channel

        self._current_filename = path.name

        self._start_time = monotonic()

        self._playing = True

        self._thread = threading.Thread(
            target=self._worker,
            daemon=True,
        )

        self._thread.start()

        self.logger.info(
            "Soundcheck gestartet: %s (%d Kanäle ab Kanal %d)",
            self._current_filename,
            self.reader.channels,
            start_channel + 1,
        )

        return True

    def stop(self) -> None:
        """
        Stoppt die laufende Wiedergabe.
        """

        if not self.playing:
            return

        self._playing = False

        if self._thread is not None:

            self._thread.join()

            self._thread = None

    def _worker(self) -> None:
        """
        Liest die Datei blockweise und gibt sie über ALSA aus.
        """

        frame_size = (
            self.reader.channels *
            AudioPlaybackBackend.BYTES_PER_SAMPLE
        )

        chunk_bytes = self.CHUNK_FRAMES * frame_size

        while self._playing:

            data = self.reader.read(chunk_bytes)

            if data is None:
                break

            self.backend.write(data)

        if self._start_time is not None:

            self._last_duration = (
                monotonic() - self._start_time
            )

            self._start_time = None

        self.reader.close()

        self.backend.close()

        self._playing = False

        self.logger.info(
            "Soundcheck beendet: %s",
            self._current_filename,
        )
