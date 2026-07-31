"""
Wave64-Dateileser (blockweise) für die Wiedergabe.
"""

import logging
import struct
from pathlib import Path

from writer.w64_writer import (
    RIFF_GUID,
    WAVE_GUID,
    FMT_GUID,
    DATA_GUID,
)


class W64Reader:
    """Liest eine Wave64-Datei blockweise für die Wiedergabe."""

    def __init__(self):

        self.logger = logging.getLogger("XRack")

        self.file = None

        self.channels = 0
        self.sample_rate = 0
        self.bits_per_sample = 0

        self._data_size = 0
        self._bytes_read = 0

    def open(self, filename: str | Path) -> None:
        """
        Öffnet die Datei und liest den Header.
        """

        self.file = open(
            filename,
            "rb",
        )

        self._read_riff_chunk()

        self._read_fmt_chunk()

        self._read_data_chunk_header()

        self._bytes_read = 0

        self.logger.info(
            "W64-Datei geöffnet: %s | %d Ch | %d Hz",
            filename,
            self.channels,
            self.sample_rate,
        )

    def read(self, chunk_size: int) -> bytes | None:
        """
        Liest bis zu chunk_size Bytes PCM-Daten.
        Liefert None, wenn das Dateiende erreicht ist.
        """

        if self.file is None:
            return None

        remaining = self._data_size - self._bytes_read

        if remaining <= 0:
            return None

        data = self.file.read(
            min(chunk_size, remaining)
        )

        if not data:
            return None

        self._bytes_read += len(data)

        return data

    def close(self) -> None:
        """
        Schließt die Datei.
        """

        if self.file is not None:

            self.file.close()

            self.file = None

    def _read_riff_chunk(self) -> None:
        """
        Liest den RIFF-Chunk.
        """

        guid = self.file.read(16)

        if guid != RIFF_GUID:
            raise ValueError(
                "Keine Wave64-Datei."
            )

        #
        # Dateigröße
        #

        self.file.read(8)

        wave = self.file.read(16)

        if wave != WAVE_GUID:
            raise ValueError(
                "Ungültiger Wave64-Header."
            )

    def _read_fmt_chunk(self) -> None:
        """
        Liest den fmt-Chunk.
        """

        guid = self.file.read(16)

        if guid != FMT_GUID:
            raise ValueError(
                "fmt-Chunk fehlt."
            )

        #
        # Chunkgröße
        #

        self.file.read(8)

        #
        # FormatTag
        #

        self.file.read(2)

        #
        # Kanäle
        #

        self.channels = struct.unpack(
            "<H",
            self.file.read(2),
        )[0]

        #
        # Samplerate
        #

        self.sample_rate = struct.unpack(
            "<I",
            self.file.read(4),
        )[0]

        #
        # AvgBytesPerSec, BlockAlign, wBitsPerSample, cbSize
        #

        self.file.read(4)
        self.file.read(2)
        self.file.read(2)
        self.file.read(2)

        #
        # ValidBitsPerSample
        #

        self.bits_per_sample = struct.unpack(
            "<H",
            self.file.read(2),
        )[0]

        #
        # ChannelMask
        #

        self.file.read(4)

        #
        # SubFormat GUID
        #

        self.file.read(16)

    def _read_data_chunk_header(self) -> None:
        """
        Liest den Kopf des data-Chunks (ohne die Nutzdaten).
        """

        guid = self.file.read(16)

        if guid != DATA_GUID:
            raise ValueError(
                "data-Chunk fehlt."
            )

        self._data_size = struct.unpack(
            "<Q",
            self.file.read(8),
        )[0]
