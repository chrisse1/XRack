"""
XRack Recorder.
"""

import logging
import threading

from audio.audio_backend import AudioBackend
from writer.audio_writer import AudioWriter
from writer.w64_writer import W64Writer
from time import monotonic


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
        
        self.writer.close()

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

        self._recording = True

        self.writer.open()

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

        self._recording = False
        
        if self._thread is not None:

            self._thread.join()

            self._thread = None
            
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
                        self._bytes_written / 1024 / 1024,
                    )

            self.writer.write(data)
            
            self._buffer_count += 1
            
            self._bytes_written += len(data)

        self.logger.info(
            "Recorder-Thread beendet."
    )
    
    @property
    def buffer_count(self) -> int:
        return self._buffer_count

    @property
    def bytes_written(self) -> int:
        return self._bytes_written
        
    @property
    def duration(self) -> float:

        if self._start_time is None:
            return 0.0

        return monotonic() - self._start_time
        
    @property
    def megabytes_written(self) -> float:

        return self._bytes_written / 1024 / 1024


    @property
    def gigabytes_written(self) -> float:

        return self._bytes_written / 1024 / 1024 / 1024
