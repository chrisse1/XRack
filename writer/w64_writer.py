"""
Wave64-Dateischreiber.
"""

import logging

from writer.audio_writer import AudioWriter


class W64Writer(AudioWriter):

    def __init__(self):

        super().__init__()

        self.logger = logging.getLogger("XRack")

        self.file = None

    def open(self):

        self.logger.info(
            "W64-Datei geöffnet."
        )

    def write(self, data: bytes):

        #
        # Noch leer
        #

        pass

    def close(self):

        self.logger.info(
            "W64-Datei geschlossen."
        )
