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

        filename = self.create_filename(
            "w64"
        )

        self.file = open(
            filename,
            "wb",
        )

        self.logger.info(
            "W64-Datei geöffnet: %s",
            filename,
        )

    def write(self, data: bytes):

        #
        # Noch leer
        #

        pass

    def close(self):

        if self.file is not None:

            self.file.close()

            self.file = None

        self.logger.info(
            "W64-Datei geschlossen."
        )
