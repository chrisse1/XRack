"""
Kombiniert mehrere Stereo-Audiodateien ("Stems", z.B. Click,
eigenes Instrument, Rest der Band aus Moises) zu einer einzigen
Mehrkanal-.w64-Aufnahme ("Übungsmix") - siehe
core/application.py:start_stem_combine().

Nutzt ausschließlich schon vorhandene, bewährte Bausteine: ffmpeg
(über player/track_decoder.py:TrackDecoder, genau wie beim
Musikspieler) zum Dekodieren/Resampling jeder Quelldatei, und
XRacks eigenen writer/w64_writer.py:W64Writer zum Schreiben - das
Ergebnis ist dadurch garantiert mit reader/w64_reader.py kompatibel,
im Gegensatz zu extern (z.B. per ffmpeg-Remux) erzeugten .w64-
Dateien, die XRacks eigener, auf die selbstgeschriebene Struktur
festgelegter Reader nicht zuverlässig lesen kann.

Zum Sample-Format: XRacks Dateien enthalten real volle S32_LE-Samples.
audio/audio_backend.py fordert zwar PCM_FORMAT_S24_LE an, wertet den
Rückgabewert von setformat() aber nicht aus - die X-Serie bietet dieses
Format über USB offenbar nicht an, sodass ALSA S32_LE liefert. Da
Aufnahme und Wiedergabe dasselbe anfordern und dasselbe bekommen, hebt
sich das im Betrieb auf und fällt nicht auf. ffmpeg liefert ebenfalls
S32_LE, hier ist also gar keine Umrechnung nötig - die Rohblöcke werden
direkt interleaved. (Eine Umrechnung auf 24 Bit war der Grund, warum
frühere Übungsmixe rund 48 dB zu leise waren.)
"""

from pathlib import Path

from core.recording_kind import MARKER_PRACTICE
from player.track_decoder import TrackDecoder, probe_duration
from writer.w64_writer import W64Writer

CHUNK_FRAMES = 4096
BYTES_PER_SAMPLE = 4
STEREO_FRAME_BYTES = 2 * BYTES_PER_SAMPLE


class StemCombineError(Exception):
    """
    Fehler während combine_stems() - die Nachricht ist für die
    Anzeige im Frontend gedacht.
    """


def combine_stems(
    paths: list[Path],
    target_rate: int,
    name_prefix: str,
    writer: W64Writer | None = None,
) -> str:
    """
    Kombiniert die Stereo-Dateien aus `paths` (Reihenfolge = Kanal-
    zuordnung, Datei 1 -> Kanal 1+2, Datei 2 -> Kanal 3+4, ...) zu
    einer Mehrkanal-.w64-Datei mit `target_rate` Hz. Kürzere Dateien
    werden bis zur Länge der längsten mit Stille aufgefüllt, statt
    abgeschnitten zu werden. Liefert den erzeugten Dateinamen.

    Wirft StemCombineError bei ungültiger Eingabe oder wenn eine
    Datei nicht gelesen werden kann - dann wird keine Ausgabedatei
    angelegt.
    """

    if not 2 <= len(paths) <= 8:
        raise StemCombineError(
            "Es werden 2 bis 8 Dateien benötigt."
        )

    durations = [probe_duration(path) for path in paths]

    if any(duration <= 0 for duration in durations):
        raise StemCombineError(
            "Mindestens eine Datei konnte nicht gelesen werden "
            "(beschädigt oder nicht unterstütztes Format?)."
        )

    target_frames = round(max(durations) * target_rate)

    channels = len(paths) * 2

    decoders = [TrackDecoder() for _ in paths]

    try:

        for decoder, path in zip(decoders, paths):

            if not decoder.open(path, channels=2, rate=target_rate):
                raise StemCombineError(
                    "ffmpeg wurde nicht gefunden - bitte auf dem "
                    "Raspberry Pi installieren (sudo apt install ffmpeg)."
                )

        if writer is None:
            writer = W64Writer()

        writer.open(
            channels=channels,
            sample_rate=target_rate,
            bits_per_sample=24,
            name_prefix=name_prefix,
            marker=MARKER_PRACTICE,
        )

        exhausted = [False] * len(decoders)

        written_frames = 0

        while written_frames < target_frames:

            block_frames = min(
                CHUNK_FRAMES,
                target_frames - written_frames,
            )

            block_bytes = block_frames * STEREO_FRAME_BYTES

            per_source_blocks = []

            for index, decoder in enumerate(decoders):

                if exhausted[index]:
                    per_source_blocks.append(bytes(block_bytes))
                    continue

                raw = b""

                while len(raw) < block_bytes:

                    chunk = decoder.read(block_bytes - len(raw))

                    if chunk is None:
                        exhausted[index] = True
                        break

                    raw += chunk

                if len(raw) < block_bytes:
                    #
                    # Diese Quelle ist kürzer als die längste - mit
                    # Stille auffüllen, damit alle Spuren synchron
                    # bleiben.
                    #
                    raw += bytes(block_bytes - len(raw))

                #
                # Keine Umrechnung nötig: TrackDecoder/ffmpeg liefert
                # bereits S32_LE - genau das Format, das auch beim
                # Aufnehmen von ALSA kommt und unverändert in die Datei
                # geschrieben wird (siehe Modul-Docstring oben).
                #
                per_source_blocks.append(raw)

            out_chunk = bytearray(
                block_frames * channels * BYTES_PER_SAMPLE
            )

            for frame in range(block_frames):

                dst_frame_offset = (
                    frame * channels * BYTES_PER_SAMPLE
                )

                for source_index, block in enumerate(per_source_blocks):

                    src_offset = frame * STEREO_FRAME_BYTES

                    dst_offset = (
                        dst_frame_offset
                        + source_index * STEREO_FRAME_BYTES
                    )

                    out_chunk[dst_offset:dst_offset + STEREO_FRAME_BYTES] = (
                        block[src_offset:src_offset + STEREO_FRAME_BYTES]
                    )

            writer.write(bytes(out_chunk))

            written_frames += block_frames

        filename = Path(writer.filename).name

        writer.close()

        return filename

    finally:

        for decoder in decoders:
            decoder.close()
