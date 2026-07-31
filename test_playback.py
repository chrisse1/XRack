"""
Prüft W64Reader (Roundtrip mit W64Writer) und ChannelInserter
(Gegenstück zu ChannelExtractor für die Soundcheck-Wiedergabe).

Testet bewusst nicht AudioPlaybackBackend, da dafür das ALSA-Modul
(alsaaudio) und echte Hardware nötig sind - das ist nur auf dem
Raspberry Pi selbst möglich.
"""

import tempfile
from pathlib import Path

from audio.channel_extractor import ChannelExtractor
from audio.channel_inserter import ChannelInserter
from reader.w64_reader import W64Reader
from writer.w64_writer import W64Writer

BYTES_PER_SAMPLE = 4


def make_frame(channels: int, marker: int) -> bytes:
    """
    Baut einen Frame, bei dem Kanal 0 den Marker-Wert trägt.
    """

    frame = bytearray(channels * BYTES_PER_SAMPLE)
    frame[0] = marker
    return bytes(frame)


def channel_value(frame: bytes, channel: int) -> int:
    offset = channel * BYTES_PER_SAMPLE
    return frame[offset]


# ----------------------------------------------------------------
# 1. W64Writer -> W64Reader Roundtrip
# ----------------------------------------------------------------

with tempfile.TemporaryDirectory() as tmp_dir:

    writer = W64Writer()
    writer.directory = Path(tmp_dir)

    channels = 8
    frame_count = 50

    writer.open(
        channels=channels,
        sample_rate=48000,
        bits_per_sample=24,
    )

    written = b"".join(
        make_frame(channels, marker=1) for _ in range(frame_count)
    )

    writer.write(written)

    writer.close()

    reader = W64Reader()
    reader.open(writer.filename)

    assert reader.channels == channels
    assert reader.sample_rate == 48000

    read_back = b""
    while True:
        chunk = reader.read(64)
        if chunk is None:
            break
        read_back += chunk

    reader.close()

    assert read_back == written, "W64Reader liefert nicht dieselben Daten wie geschrieben."

    print(f"OK: W64Writer/W64Reader Roundtrip ({len(read_back)} Bytes)")

# ----------------------------------------------------------------
# 2. ChannelInserter: Kanal 0 bleibt auf Kanal 0, Rest bleibt stumm
# ----------------------------------------------------------------

for input_channels in (18, 8, 2):

    inserter = ChannelInserter(
        input_channels=input_channels,
        output_channels=18,
    )

    frame_count = 20

    data = b"".join(
        make_frame(input_channels, marker=1) for _ in range(frame_count)
    )

    result = inserter.insert(data)

    expected_length = frame_count * 18 * BYTES_PER_SAMPLE
    assert len(result) == expected_length, (
        f"{input_channels} -> 18 Kanäle: Länge falsch "
        f"({len(result)} statt {expected_length})"
    )

    for frame_index in range(frame_count):
        frame_offset = frame_index * 18 * BYTES_PER_SAMPLE
        frame = result[frame_offset:frame_offset + 18 * BYTES_PER_SAMPLE]

        assert channel_value(frame, 0) == 1, (
            f"{input_channels} -> 18 Kanäle, Frame {frame_index}: "
            f"Marker nicht auf Kanal 0."
        )

        for other_channel in range(1, 18):
            assert channel_value(frame, other_channel) == 0, (
                f"{input_channels} -> 18 Kanäle, Frame {frame_index}: "
                f"Kanal {other_channel} ist nicht stumm."
            )

    print(f"OK: ChannelInserter {input_channels} -> 18 Kanäle ({len(result)} Bytes)")

# ----------------------------------------------------------------
# 3. Extractor + Inserter: voller Roundtrip (Aufnahme -> Wiedergabe)
# ----------------------------------------------------------------

extractor = ChannelExtractor(input_channels=18, output_channels=8)
inserter = ChannelInserter(input_channels=8, output_channels=18)

native_frames = b"".join(
    make_frame(18, marker=1) for _ in range(30)
)

recorded = extractor.extract(native_frames)
played_back = inserter.insert(recorded)

assert len(played_back) == len(native_frames)

for frame_index in range(30):
    frame_offset = frame_index * 18 * BYTES_PER_SAMPLE
    frame = played_back[frame_offset:frame_offset + 18 * BYTES_PER_SAMPLE]
    assert channel_value(frame, 0) == 1

print("OK: Extractor -> Inserter Roundtrip (Aufnahme -> Soundcheck)")

print("Alle Tests erfolgreich.")
