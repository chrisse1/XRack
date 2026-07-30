"""
Prüft, dass ChannelExtractor Kanäle sauber herausschneidet,
ohne Datenversatz (der Bug, der zu falscher Dauer und
wandernden Kanälen führte).
"""

from audio.channel_extractor import ChannelExtractor

BYTES_PER_SAMPLE = 4
INPUT_CHANNELS = 18


def make_frame(marker: int) -> bytes:
    """
    Baut einen 18-Kanal-Frame, bei dem Kanal 0 den
    übergebenen Marker-Wert trägt und alle anderen Kanäle 0 sind.
    """

    frame = bytearray(INPUT_CHANNELS * BYTES_PER_SAMPLE)
    frame[0] = marker
    return bytes(frame)


def channel_value(frame: bytes, channel: int) -> int:
    offset = channel * BYTES_PER_SAMPLE
    return frame[offset]


for output_channels in (18, 8, 2):

    extractor = ChannelExtractor(
        input_channels=INPUT_CHANNELS,
        output_channels=output_channels,
    )

    frame_count = 20

    data = b"".join(
        make_frame(marker=1) for _ in range(frame_count)
    )

    result = extractor.extract(data)

    #
    # Keine Aufblähung/Schrumpfung der Länge -> Dauer bleibt korrekt
    #
    expected_length = frame_count * output_channels * BYTES_PER_SAMPLE
    assert len(result) == expected_length, (
        f"{output_channels} Kanäle: Länge falsch "
        f"({len(result)} statt {expected_length})"
    )

    #
    # Der Marker muss in JEDEM Frame stabil auf Kanal 0 liegen,
    # nicht über 1,3,5,7 ... wandern.
    #
    for frame_index in range(frame_count):
        frame_offset = frame_index * output_channels * BYTES_PER_SAMPLE
        frame = result[frame_offset:frame_offset + output_channels * BYTES_PER_SAMPLE]

        assert channel_value(frame, 0) == 1, (
            f"{output_channels} Kanäle, Frame {frame_index}: "
            f"Marker nicht auf Kanal 0."
        )

        for other_channel in range(1, output_channels):
            assert channel_value(frame, other_channel) == 0, (
                f"{output_channels} Kanäle, Frame {frame_index}: "
                f"Marker ist auf Kanal {other_channel} durchgesickert."
            )

    print(f"OK: {output_channels} Kanäle ({len(result)} Bytes)")

print("Alle Tests erfolgreich.")
