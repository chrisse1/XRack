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

        #
        # Die GUELTIGEN Bits je Wert (24) - nicht die Behaeltergroesse.
        #
        self.bits_per_sample = 0

        #
        # Die Behaeltergroesse (32) und die Groesse eines ganzen
        # Rahmens. Nur damit laesst sich rechnen, siehe frame_bytes.
        #
        self.container_bits = 0
        self.block_align = 0

        self._data_size = 0
        self._bytes_read = 0

        #
        # Wo die Nutzdaten anfangen. Gebraucht wird das zum Spulen -
        # zum Ueben will man eine Stelle wiederholen, nicht das Stueck
        # von vorn hoeren.
        #
        self._data_start = 0

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

    @property
    def frame_bytes(self) -> int:
        """
        Wie viele Byte ein Rahmen belegt (alle Kanäle zusammen).

        Aus BlockAlign, nicht aus den Bits gerechnet: XRacks Dateien
        tragen 24 gültige Bits in einem 32-Bit-Behälter, ein Wert
        belegt also vier Byte und nicht drei.
        """

        if self.block_align:
            return self.block_align

        return self.channels * ((self.container_bits or 32) // 8)

    @property
    def duration(self) -> float:
        """Die Länge in Sekunden, aus dem Kopf gerechnet."""

        je_sekunde = self.frame_bytes * self.sample_rate

        if je_sekunde <= 0:
            return 0.0

        return self._data_size / je_sekunde

    def seek(self, position: float) -> None:
        """
        An eine Stelle springen (Sekunden vom Anfang).

        Gerundet wird auf ganze Rahmen: Mitten in einem Rahmen
        anzufangen hiesse, dass ab dort alle Kanäle um einen Wert
        verschoben sind - man hört den Bass auf der Stimme.
        """

        if self.file is None:
            return

        rahmen = self.frame_bytes

        if rahmen <= 0:
            return

        versatz = max(0, int(position * self.sample_rate)) * rahmen

        versatz = min(versatz, self._data_size)

        self.file.seek(self._data_start + versatz)

        self._bytes_read = versatz

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
        # AvgBytesPerSec
        #

        self.file.read(4)

        #
        # BlockAlign - die GROESSE EINES RAHMENS, und damit die einzige
        # verlaessliche Angabe darueber, wie viele Byte ein Wert
        # belegt.
        #
        # Sie wurde frueher uebersprungen, und daraus wurde beinahe ein
        # Fehler: Gerechnet haette man sonst mit ValidBitsPerSample
        # (24 Bit = 3 Byte), tatsaechlich belegt ein Wert aber vier
        # Byte (32-Bit-Behaelter, 24 gueltige Bits). Die Laenge einer
        # Datei kaeme damit um ein Drittel zu lang heraus, und jeder
        # Sprung landete an der falschen Stelle.
        #
        # Genau in diese Falle tappt uebrigens ffmpeg bei unseren
        # Dateien - siehe player/w64_decoder.py.
        #
        self.block_align = struct.unpack(
            "<H",
            self.file.read(2),
        )[0]

        #
        # wBitsPerSample (Behaeltergroesse) und cbSize
        #

        self.container_bits = struct.unpack(
            "<H",
            self.file.read(2),
        )[0]

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

        self._data_start = self.file.tell()
