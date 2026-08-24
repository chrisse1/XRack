"""
Wave64-Dateischreiber.
"""

import logging
import struct
from uuid import UUID

from core.recording_kind import MARKER_SOUNDCHECK
from writer.audio_writer import AudioWriter


RIFF_GUID = UUID(
    "66666972-912E-11CF-A5D6-28DB04C10000"
).bytes_le

WAVE_GUID = UUID(
    "65766177-ACF3-11D3-8CD1-00C04F8EDB8A"
).bytes_le

FMT_GUID = UUID(
    "20746D66-ACF3-11D3-8CD1-00C04F8EDB8A"
).bytes_le
DATA_GUID = UUID(
    "61746164-ACF3-11D3-8CD1-00C04F8EDB8A"
).bytes_le

class W64Writer(AudioWriter):

    def __init__(self):

        super().__init__()

        self.logger = logging.getLogger("XRack")

        self.file = None
        
        self._data_size_offset = 0
        
        self._data_start = 0

    def open(
        self,
        channels: int,
        sample_rate: int,
        bits_per_sample: int,
        name_prefix: str = "Soundcheck",
        marker: str = MARKER_SOUNDCHECK,
    ):

        self.channels = channels
        self.sample_rate = sample_rate
        self.bits_per_sample = bits_per_sample

        filename = self.create_filename(
            "w64",
            prefix=name_prefix,
            marker=marker,
        )

        self.file = open(
            filename,
            "wb",
        )

        self._write_header()

        self.logger.info(
            "W64-Datei geöffnet: %s",
            filename,
        )

    def write(
        self,
        data: bytes,
    ):

        if self.file is None:
            return

        self.file.write(data)

    def close(self):

        if self.file is not None:
        
            file_size = self.file.tell()

            #
            # RIFF-Größe
            #

            self.file.seek(16)

            self.file.write(
                struct.pack("<Q", file_size)
            )

            #
            # DATA-Größe
            #

            data_size = file_size - self._data_start

            self.file.seek(
                self._data_size_offset
            )

            self.file.write(
                struct.pack("<Q", data_size)
            )

            self.file.seek(file_size)

            self.file.close()

            self.file = None

            self.logger.info(
                "W64-Datei geschlossen."
            )

    def _write_header(self) -> None:
        """
        Schreibt den Wave64-Header.
        """

        self._write_riff_chunk()

        self._write_fmt_chunk()

        self._write_data_chunk()

    def _write_riff_chunk(self) -> None:
        """
        Schreibt den RIFF-Chunk.
        """

        self.file.write(RIFF_GUID)

        #
        # Platzhalter für Dateigröße
        #

        self.file.write(
            struct.pack("<Q", 0)
        )

        self.file.write(
            WAVE_GUID
        )

    def _write_fmt_chunk(self) -> None:
        """
        Schreibt zunächst nur den fmt-Chunk-Kopf.
        """

        self.file.write(FMT_GUID)

        #
        # Chunkgröße
        #

        self.file.write(
            struct.pack("<Q", 64)
        )

        #
        # WAVE_FORMAT_EXTENSIBLE
        #
        self.file.write(
            struct.pack("<H", 0xFFFE)
        )

        #
        # Anzahl Kanäle
        #
        self.file.write(
            struct.pack(
                "<H",
                self.channels,
            )
        )

        #
        # Samplerate
        #
        self.file.write(
            struct.pack(
                "<I",
                self.sample_rate,
            )
        )
        #
        # nAvgBytesPerSec
        #
        block_align = self.channels * 4

        self.file.write(
            struct.pack(
                "<I",
                self.sample_rate * block_align,
            )
        )

        #
        # nBlockAlign
        #
        self.file.write(
            struct.pack(
                "<H",
                block_align,
            )
        )

        #
        # wBitsPerSample
        #
        self.file.write(
            struct.pack(
                "<H",
                32,
            )
        )
        #
        # cbSize
        #
        self.file.write(
            struct.pack("<H", 22)
        )

        #
        # ValidBitsPerSample
        #
        self.file.write(
            struct.pack("<H", 24)
        )

        #
        # ChannelMask
        #
        self.file.write(
            struct.pack("<I", 0)
        )

        #
        # SubFormat GUID (PCM)
        #
        self.file.write(
            UUID(
                "00000001-0000-0010-8000-00AA00389B71"
            ).bytes_le
        )
        
    def _write_data_chunk(self) -> None:
        """
        Schreibt den data-Chunk.
        """

        self.file.write(DATA_GUID)

        self._data_size_offset = self.file.tell()

        self.file.write(
            struct.pack("<Q", 0)
        )

        self._data_start = self.file.tell()
