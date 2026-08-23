#!/usr/bin/env python3
"""
Fügt mehrere Stereo-WAV-Dateien zu einer einzigen Mehrkanal-.w64-Datei
zusammen, die sich direkt mit XRack abspielen lässt (Soundcheck-
Wiedergabe, Aufnahmen-Liste).

Beispiel (3 Stereo-Dateien -> Kanal 1-6):

    python3 tools/combine_stereo_to_w64.py \\
        Drums.wav Keys.wav Vocals.wav \\
        -o recordings/Mix-1.w64

Datei 1 landet auf Kanal 1+2, Datei 2 auf Kanal 3+4, Datei 3 auf
Kanal 5+6 usw. - beliebig viele Dateien möglich, nicht nur drei.

Haben die Eingabedateien nicht alle dieselbe Samplerate, oder soll
das Ergebnis eine andere Samplerate haben als die Quellen (z.B.
Quellen mit 44,1 kHz, Ziel 48 kHz für die Konsole), per
"-r 48000"/"--samplerate 48000" angeben - abweichende Dateien werden
dann automatisch per ffmpeg umgerechnet (echtes Resampling, nicht nur
ein anderer Header-Eintrag). Ohne diese Option müssen alle
Eingabedateien bereits dieselbe Samplerate haben.

Das Skript ist bewusst eigenständig (keine Abhängigkeit vom
restlichen XRack-Code, nur Python-Standardbibliothek + ffmpeg als
externer Prozess fürs Resampling) und lässt sich sowohl direkt auf
dem Raspberry Pi als auch auf einem beliebigen anderen Rechner
ausführen (ffmpeg ist ohnehin bereits Voraussetzung für XRack selbst,
siehe player/track_decoder.py). Läuft es nicht auf dem Pi, lässt sich
die erzeugte .w64-Datei anschließend über den "Hochladen"-Knopf im
Aufnahmen-Modal auf XRack übertragen.

Format-Hinweis: XRacks eigenes .w64-Format speichert Samples
IMMER als 24-Bit-Werte in einem 4-Byte-Container (die oberen 8 Bit
bleiben ungenutzt/Null) - unabhängig von der Bittiefe der
Eingabedateien. 8/16/24/32-Bit-PCM-WAV-Dateien werden beim
Zusammenführen automatisch dorthin umgerechnet.
"""

import argparse
import shutil
import subprocess
import tempfile
import struct
import sys
from pathlib import Path
from uuid import UUID

#
# Dieselben GUIDs/derselbe Header-Aufbau wie writer/w64_writer.py -
# absichtlich hier dupliziert, damit dieses Skript ohne den Rest von
# XRack lauffähig bleibt.
#
RIFF_GUID = UUID("66666972-912E-11CF-A5D6-28DB04C10000").bytes_le
WAVE_GUID = UUID("65766177-ACF3-11D3-8CD1-00C04F8EDB8A").bytes_le
FMT_GUID = UUID("20746D66-ACF3-11D3-8CD1-00C04F8EDB8A").bytes_le
DATA_GUID = UUID("61746164-ACF3-11D3-8CD1-00C04F8EDB8A").bytes_le
PCM_SUBFORMAT_GUID = UUID("00000001-0000-0010-8000-00AA00389B71").bytes_le

BYTES_PER_SAMPLE = 4  # 24 Bit gültig, in einem 4-Byte-Container
CHUNK_FRAMES = 8192  # Frames pro Verarbeitungsblock (Speicher schonen)


def write_w64_header(file, channels: int, sample_rate: int) -> int:
    """
    Schreibt den Wave64-Header (RIFF-/DATA-Größe zunächst als
    Platzhalter). Gibt die Dateiposition zurück, an der die
    DATA-Größe später nachgetragen werden muss.
    """

    file.write(RIFF_GUID)
    file.write(struct.pack("<Q", 0))  # Platzhalter Dateigröße
    file.write(WAVE_GUID)

    file.write(FMT_GUID)
    file.write(struct.pack("<Q", 64))  # Chunkgröße
    file.write(struct.pack("<H", 0xFFFE))  # WAVE_FORMAT_EXTENSIBLE
    file.write(struct.pack("<H", channels))
    file.write(struct.pack("<I", sample_rate))

    block_align = channels * BYTES_PER_SAMPLE
    file.write(struct.pack("<I", sample_rate * block_align))  # AvgBytesPerSec
    file.write(struct.pack("<H", block_align))
    file.write(struct.pack("<H", 32))  # wBitsPerSample (Container)
    file.write(struct.pack("<H", 22))  # cbSize
    file.write(struct.pack("<H", 24))  # ValidBitsPerSample
    file.write(struct.pack("<I", 0))  # ChannelMask
    file.write(PCM_SUBFORMAT_GUID)

    file.write(DATA_GUID)
    data_size_offset = file.tell()
    file.write(struct.pack("<Q", 0))  # Platzhalter DATA-Größe

    return data_size_offset


def finalize_w64_header(file, data_size_offset: int) -> None:
    """Trägt RIFF-/DATA-Größe nachträglich ein (siehe write_w64_header())."""

    file_size = file.tell()

    file.seek(16)
    file.write(struct.pack("<Q", file_size))

    data_size = file_size - (data_size_offset + 8)
    file.seek(data_size_offset)
    file.write(struct.pack("<Q", data_size))

    file.seek(file_size)


def sample_to_int24(raw: bytes, width: int) -> int:
    """
    Wandelt einen einzelnen Sample-Wert (raw, width Bytes) in einen
    24-Bit-Integer (-8388608..8388607) um.
    """

    if width == 1:
        # 8-Bit-WAV ist unüblich unsigned (0..255)
        return (raw[0] - 128) << 16

    if width == 2:
        value16 = struct.unpack("<h", raw)[0]
        return value16 << 8

    if width == 3:
        return int.from_bytes(raw, "little", signed=True)

    if width == 4:
        value32 = struct.unpack("<i", raw)[0]
        return value32 >> 8

    raise ValueError(f"Nicht unterstützte Bittiefe: {width * 8} Bit")


def pack_int24(value: int) -> bytes:
    """Packt einen 24-Bit-Wert in den 4-Byte-Container (oberstes Byte 0)."""

    return struct.pack("<I", value & 0xFFFFFF)


SILENCE_SAMPLE = pack_int24(0)


class WavFile:
    """
    Minimaler, eigenständiger WAV-Header-Parser.

    Python's eingebautes wave-Modul kann nur klassisches PCM
    (Format-Tag 1) lesen und scheitert an WAVE_FORMAT_EXTENSIBLE
    (Format-Tag 0xFFFE) mit "unknown format: 65534" - genau das
    Format, das viele DAWs für 24-Bit-Exporte verwenden UND das
    ffmpeg beim Resampling auf pcm_s24le selbst erzeugt. Dieser
    Parser versteht beide Varianten.
    """

    def __init__(self, path: Path):
        self.path = path
        self.file = open(path, "rb")

        if self.file.read(4) != b"RIFF":
            raise ValueError(f"{path.name}: keine gültige WAV-Datei.")

        self.file.read(4)  # Dateigröße - wird nicht gebraucht

        if self.file.read(4) != b"WAVE":
            raise ValueError(f"{path.name}: keine gültige WAV-Datei.")

        self.channels = 0
        self.sample_rate = 0
        self.container_width = 0  # Bytes pro Sample/Kanal
        self.data_offset: int | None = None
        self.data_size = 0

        fmt_seen = False

        while True:
            header = self.file.read(8)
            if len(header) < 8:
                break

            chunk_id = header[0:4]
            chunk_size = struct.unpack("<I", header[4:8])[0]
            chunk_start = self.file.tell()

            if chunk_id == b"fmt ":
                self._read_fmt_chunk(chunk_size)
                fmt_seen = True
            elif chunk_id == b"data":
                self.data_offset = chunk_start
                self.data_size = chunk_size
                if fmt_seen:
                    break

            # RIFF-Chunks sind auf gerade Länge gepolstert.
            self.file.seek(chunk_start + chunk_size + (chunk_size % 2))

        if not fmt_seen or self.data_offset is None:
            raise ValueError(f"{path.name}: fmt- oder data-Chunk fehlt.")

        self.file.seek(self.data_offset)

    def _read_fmt_chunk(self, chunk_size: int) -> None:

        (
            format_tag,
            self.channels,
            self.sample_rate,
            _avg_bytes_per_sec,
            _block_align,
            bits_per_sample,
        ) = struct.unpack("<HHIIHH", self.file.read(16))

        effective_tag = format_tag
        valid_bits = bits_per_sample

        if format_tag == 0xFFFE and chunk_size >= 40:
            cb_size = struct.unpack("<H", self.file.read(2))[0]
            if cb_size >= 22:
                valid_bits_raw = struct.unpack("<H", self.file.read(2))[0]
                if valid_bits_raw:
                    valid_bits = valid_bits_raw
                self.file.read(4)  # ChannelMask
                subformat = self.file.read(16)
                effective_tag = struct.unpack("<H", subformat[0:2])[0]

        if effective_tag != 1:
            raise ValueError(
                f"{self.path.name}: nicht unterstütztes WAV-Format - "
                "nur PCM wird unterstützt (keine Fließkomma-/"
                "komprimierten Dateien)."
            )

        self.container_width = bits_per_sample // 8
        self.bits_per_sample = valid_bits

        if self.container_width not in (1, 2, 3, 4):
            raise ValueError(
                f"{self.path.name}: nicht unterstützte Bittiefe "
                f"({bits_per_sample} Bit)."
            )

    def read_raw(self, n_bytes: int) -> bytes:
        remaining = self.data_offset + self.data_size - self.file.tell()
        return self.file.read(min(n_bytes, max(remaining, 0)))

    def close(self) -> None:
        self.file.close()


class StereoSource:
    """
    Liest eine Stereo-WAV-Datei blockweise und liefert für jeden
    Frame ein (links, rechts)-Samplepaar als fertig gepackte 4-Byte-
    Container. Liefert Stille, sobald die Datei zu Ende ist (die
    kürzeren Dateien werden so bis zur Länge der längsten aufgefüllt,
    damit alle Spuren synchron bleiben).
    """

    def __init__(self, path: Path):
        self.path = path
        self.wav = WavFile(path)

        if self.wav.channels != 2:
            raise ValueError(
                f"{path.name}: hat {self.wav.channels} Kanäle, "
                "erwartet werden genau 2 (Stereo)."
            )

        self.width = self.wav.container_width
        self.sample_rate = self.wav.sample_rate

        frame_size = 2 * self.width
        self.total_frames = self.wav.data_size // frame_size
        self._exhausted = False

    def read_block(self, n_frames: int) -> list[bytes]:
        """
        Liefert bis zu n_frames (links, rechts)-Samplepaare als Liste
        von je 8 Bytes (4 Byte links + 4 Byte rechts), mit Stille
        aufgefüllt, falls die Datei bereits zu Ende ist.
        """

        pairs = []

        if not self._exhausted:
            frame_size = 2 * self.width
            raw = self.wav.read_raw(n_frames * frame_size)
            frames_read = len(raw) // frame_size

            if frames_read < n_frames:
                self._exhausted = True

            for i in range(frames_read):
                offset = i * frame_size
                left = raw[offset: offset + self.width]
                right = raw[offset + self.width: offset + 2 * self.width]
                pairs.append(
                    pack_int24(sample_to_int24(left, self.width))
                    + pack_int24(sample_to_int24(right, self.width))
                )

        while len(pairs) < n_frames:
            pairs.append(SILENCE_SAMPLE + SILENCE_SAMPLE)

        return pairs

    def close(self) -> None:
        self.wav.close()


def resample_wav(path: Path, target_rate: int, tmp_dir: Path) -> Path:
    """
    Wandelt eine WAV-Datei per ffmpeg auf eine andere Samplerate um
    (echtes Resampling, nicht nur ein geänderter Header-Eintrag) -
    das Ergebnis landet als neue Datei in tmp_dir.
    """

    if shutil.which("ffmpeg") is None:
        raise ValueError(
            "ffmpeg wird benötigt, um unterschiedliche Sampleraten "
            "anzugleichen, ist aber nicht installiert "
            "(sudo apt install ffmpeg)."
        )

    output_path = tmp_dir / f"{path.stem}__{target_rate}Hz.wav"

    result = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-nostdin", "-y",
            "-i", str(path),
            "-ar", str(target_rate),
            "-c:a", "pcm_s24le",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0 or not output_path.exists():
        raise ValueError(
            f"{path.name}: Umwandlung auf {target_rate} Hz per ffmpeg "
            f"fehlgeschlagen: {result.stderr.strip()}"
        )

    return output_path


def combine(
    input_paths: list[Path],
    output_path: Path,
    target_rate: int | None = None,
) -> None:

    sources = [StereoSource(path) for path in input_paths]
    tmp_dir_handle: tempfile.TemporaryDirectory | None = None

    try:
        sample_rate = target_rate if target_rate is not None else sources[0].sample_rate

        for index, source in enumerate(sources):

            if source.sample_rate == sample_rate:
                continue

            if target_rate is None:
                raise ValueError(
                    f"{source.path.name} hat {source.sample_rate} Hz, "
                    f"{input_paths[0].name} hat {sample_rate} Hz - alle "
                    "Dateien müssen dieselbe Samplerate haben, oder gib "
                    "mit -r/--samplerate eine Zielrate an, auf die "
                    "unterschiedliche Dateien automatisch umgerechnet "
                    "werden."
                )

            if tmp_dir_handle is None:
                tmp_dir_handle = tempfile.TemporaryDirectory(
                    prefix="xrack_resample_"
                )

            print(
                f"  {source.path.name}: {source.sample_rate} Hz -> "
                f"{sample_rate} Hz (ffmpeg) ..."
            )

            resampled_path = resample_wav(
                source.path,
                sample_rate,
                Path(tmp_dir_handle.name),
            )

            source.close()
            sources[index] = StereoSource(resampled_path)

        channels = len(sources) * 2
        longest = max(source.total_frames for source in sources)

        print(
            f"{len(sources)} Stereo-Datei(en) -> {channels} Kanäle, "
            f"{sample_rate} Hz, {longest / sample_rate:.1f} s"
        )
        for index, source in enumerate(sources):
            first_channel = index * 2 + 1
            print(
                f"  Kanal {first_channel}+{first_channel + 1}: "
                f"{source.path.name}"
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("wb") as out_file:

            data_size_offset = write_w64_header(
                out_file, channels, sample_rate
            )

            written = 0

            while written < longest:

                block_frames = min(CHUNK_FRAMES, longest - written)

                blocks = [
                    source.read_block(block_frames)
                    for source in sources
                ]

                #
                # Frame für Frame die Kanalpaare aller Quellen
                # aneinanderreihen (Kanal 1-2, 3-4, 5-6, ...).
                #
                out_chunk = bytearray()
                for frame_index in range(block_frames):
                    for block in blocks:
                        out_chunk += block[frame_index]

                out_file.write(out_chunk)

                written += block_frames

            finalize_w64_header(out_file, data_size_offset)

        print(f"Fertig: {output_path}")

    finally:
        for source in sources:
            source.close()

        if tmp_dir_handle is not None:
            tmp_dir_handle.cleanup()


def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "Fügt mehrere Stereo-WAV-Dateien zu einer XRack-.w64-Datei "
            "zusammen (Datei 1 -> Kanal 1+2, Datei 2 -> Kanal 3+4, ...)."
        )
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="Stereo-WAV-Dateien, in der gewünschten Kanal-Reihenfolge.",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        required=True,
        help="Ziel-.w64-Datei (z.B. recordings/Mix-1.w64).",
    )
    parser.add_argument(
        "-r", "--samplerate",
        type=int,
        default=None,
        help=(
            "Ziel-Samplerate in Hz (z.B. 48000). Ohne Angabe müssen "
            "alle Eingabedateien bereits dieselbe Samplerate haben; "
            "mit Angabe werden abweichende Dateien per ffmpeg "
            "automatisch umgerechnet (echtes Resampling)."
        ),
    )

    args = parser.parse_args()

    for path in args.inputs:
        if not path.is_file():
            print(f"Fehler: {path} existiert nicht.", file=sys.stderr)
            return 1

    try:
        combine(args.inputs, args.output, target_rate=args.samplerate)
    except ValueError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
