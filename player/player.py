"""
XRack Player (Soundcheck-Wiedergabe).
"""

import logging
import threading
from pathlib import Path
from time import monotonic

from audio.audio_playback_backend import AudioPlaybackBackend
from audio.models import AudioDevice
from reader.w64_reader import W64Reader


class Player:
    """
    Spielt eine Wave64-Aufnahme auf denselben Kanälen ab,
    auf denen sie aufgenommen wurde ("virtueller Soundcheck").
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

        if not self.backend.open(
            device,
            channels=self.reader.channels,
            rate=self.reader.sample_rate,
        ):
            self.reader.close()
            return False

        self._current_filename = path.name

        self._start_time = monotonic()

        self._playing = True

        self._thread = threading.Thread(
            target=self._worker,
            daemon=True,
        )

        self._thread.start()

        self.logger.info(
            "Soundcheck gestartet: %s",
            self._current_filename,
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
