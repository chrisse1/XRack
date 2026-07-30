"""
Liest Informationen aus einer Wave64-Datei.
"""

import struct
from pathlib import Path

from writer.w64_writer import (
    RIFF_GUID,
    WAVE_GUID,
    FMT_GUID,
    DATA_GUID,
)


class AudioFile:
    """
    Liest den Header einer Wave64-Datei.
    """

    def __init__(
        self,
        filename: str | Path,
    ):

        self.filename = Path(filename)

        self.file = None

        self.channels = 0
        self.sample_rate = 0
        self.bits_per_sample = 0

        self.data_size = 0
        self.duration = 0.0

    def open(self) -> None:
        """
        Liest den Header.
        """

        self.file = open(
            self.filename,
            "rb",
        )

        self._read_riff_chunk()

        self._read_fmt_chunk()

        self._read_data_chunk()

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
        # AvgBytesPerSec
        #

        self.file.read(4)

        #
        # BlockAlign
        #

        block_align = struct.unpack(
            "<H",
            self.file.read(2),
        )[0]

        #
        # Bits/Sample
        #

        self.file.read(2)

        #
        # cbSize
        #

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
        # PCM GUID
        #

        self.file.read(16)

        #
        # Dauer berechnen
        #

        bytes_per_second = (
            self.sample_rate *
            block_align
        )

        self._bytes_per_second = bytes_per_second

    def _read_data_chunk(self) -> None:
        """
        Liest den data-Chunk.
        """

        guid = self.file.read(16)

        if guid != DATA_GUID:
            raise ValueError(
                "data-Chunk fehlt."
            )

        self.data_size = struct.unpack(
            "<Q",
            self.file.read(8),
        )[0]

        if self._bytes_per_second > 0:

            self.duration = (
                self.data_size /
                self._bytes_per_second
            )
