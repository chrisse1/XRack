"""
XRack Recorder.
"""

import logging
import threading
import time

from audio.audio_backend import AudioBackend
from writer.audio_writer import AudioWriter
from writer.w64_writer import W64Writer
from time import monotonic
from pathlib import Path

class Recorder:
    """Verwaltet Audioaufnahmen."""

    def __init__(
        self,
        backend: AudioBackend,
    ):

        self.logger = logging.getLogger(
            "XRack"
        )

        self.backend = backend

        self._recording = False
        
        self._thread: threading.Thread | None = None
        
        self.writer: AudioWriter = W64Writer()
        
        self._buffer_count = 0

        self._bytes_written = 0
        
        self._start_time = None
        
        #
        # Statistik
        #

        self._recording = False
        self._thread = None

        self.writer = W64Writer()

        self._start_time = None

        self._buffer_count = 0
        self._bytes_written = 0

        self._current_filename = ""
        
        self._last_duration = 0.0

    @property
    def recording(self) -> bool:
        """
        True während einer Aufnahme.
        """

        return self._recording

    def start(self) -> bool:
        """
        Startet den Recorder.
        """

        if self.recording:
            return False

        self._buffer_count = 0
        self._bytes_written = 0
        self._start_time = monotonic()

        self.writer.open(
            channels=self.backend.channels,
            sample_rate=self.backend.rate,
            bits_per_sample=24,
        )
        
        self._current_filename = self.writer.filename
        
        self._recording = True

        self.logger.info(
            "Aufnahmedatei: %s",
            self._current_filename,
        )

        self.logger.info(
            "Recorder gestartet."
        )
        
        self._thread = threading.Thread(
            target=self._worker,
            daemon=True,
        )

        self._thread.start()

        return True

    def stop(self) -> None:
        """
        Stoppt den Recorder.
        """

        if not self.recording:
            return

        #
        # Dauer der Aufnahme merken
        #
        if self._start_time is not None:
            self._last_duration = (
                monotonic() - self._start_time
            )

        #
        # Recorder anhalten
        #
        self._recording = False

        if self._thread is not None:

            self._thread.join()

            self._thread = None

        #
        # Startzeit zurücksetzen
        #
        self._start_time = None

        self.writer.close()

        self.logger.info(
            "Recorder gestoppt."
        )
    
    def _worker(self) -> None:
        """
        Hauptschleife des Recorders.
        """

        self.logger.info(
            "Recorder-Thread gestartet."
        )

        while self.recording:

            data = self.backend.read()

            if data is None:

                self.logger.info(
                    "Recorder: kein Buffer"
                )

                continue

            self.writer.write(data)

            self._buffer_count += 1

            self._bytes_written += len(data)

            if self._buffer_count % 100 == 0:

                self.logger.info(
                    "Recorder: %d Buffer | %.2f MB",
                    self._buffer_count,
                    self.mb_written,
                )
    
    @property
    def buffer_count(self) -> int:
        return self._buffer_count

    @property
    def bytes_written(self) -> int:
        return self._bytes_written
        
    @property
    def duration(self) -> float:
        """
        Dauer der aktuellen bzw. letzten Aufnahme.
        """

        if self.recording:
            return monotonic() - self._start_time

        return self._last_duration
        
    @property
    def mb_written(self) -> float:

        return self._bytes_written / 1024 / 1024


    @property
    def gigabytes_written(self) -> float:

        return self._bytes_written / 1024 / 1024 / 1024
        
    @property
    def current_filename(self) -> str:
        """
        Name der aktuell aufgenommenen bzw. zuletzt aufgenommenen Datei.
        """

        return self._current_filename
        
    @property
    def recordings(self) -> list[str]:
        """
        Liefert alle vorhandenen Aufnahmen.
        """

        recording_path = Path("recordings")

        if not recording_path.exists():
            return []

        return sorted(
            [
                file.name
                for file in recording_path.glob("*.w64")
            ],
            reverse=True,
        )
