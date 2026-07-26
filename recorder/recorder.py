"""
XRack Recorder.
"""

import logging
import threading
import time

from audio.audio_backend import AudioBackend
from writer.audio_writer import AudioWriter
from writer.w64_writer import W64Writer


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

            #
            # Platzhalter
            #

            time.sleep(0.05)

        self.logger.info(
            "Recorder-Thread beendet."
    )
