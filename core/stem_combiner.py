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

Zum Sample-Format: XRacks Dateien enthalten volle S32_LE-Samples, und
genau das fordern Aufnahme und Wiedergabe inzwischen auch an (siehe
audio/audio_backend.py - früher stand dort S24_LE, was nur deshalb
richtig herauskam, weil die X-Serie dieses Format über USB nicht
anbietet). ffmpeg liefert ebenfalls S32_LE, hier ist also gar keine
Umrechnung nötig - die Rohblöcke werden direkt interleaved. (Eine
Umrechnung auf 24 Bit war der Grund, warum frühere Übungsmixe rund
48 dB zu leise waren.)
"""

from pathlib import Path

from core.recording_kind import MARKER_PRACTICE, start_channel_from_filename
from player.track_decoder import TrackDecoder, probe_duration
from reader.w64_reader import W64Reader
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
    start_channel: int = 1,
) -> str:
    """
    Kombiniert die Stereo-Dateien aus `paths` (Reihenfolge = Kanal-
    zuordnung, Datei 1 -> Kanal 1+2, Datei 2 -> Kanal 3+4, ...) zu
    einer Mehrkanal-.w64-Datei mit `target_rate` Hz. Kürzere Dateien
    werden bis zur Länge der längsten mit Stille aufgefüllt, statt
    abgeschnitten zu werden. Liefert den erzeugten Dateinamen.

    `start_channel` (1-basiert) sagt, ab welchem Kanal des Interfaces
    der Mix beim Üben liegen soll. Er wandert in den Dateinamen
    ("Probe-1_p9.w64"), wie bei Aufnahmen die Art und der erste Kanal -
    so reist die Angabe über USB, Download und Backup mit, und beim
    Üben muss sie niemand wieder eintippen (Begründung ausführlich in
    core/recording_kind.py).

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
            start_channel=start_channel,
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


def uebungsmix_mit_take(
    mix: Path,
    take: Path,
    name_prefix: str,
    versatz_ms: float = 0.0,
    writer: W64Writer | None = None,
) -> str:
    """
    Schreibt aus Übungsmix und Mitschnitt einen NEUEN Übungsmix.

    Beim Üben legt XRack beides in denselben Wiedergabestrom, ohne
    etwas zu schreiben (player/ueben_decoder.py) - das ist der richtige
    Weg fürs "mal eben anhören": nichts zu warten, ein missratener
    Versuch ist einfach gelöscht.

    Wenn ein Versuch aber sitzt, will man ihn mitnehmen: auf den Stick,
    ins Backup, auf ein anderes XRack. Dafür muss aus den zwei Dateien
    eine werden, und genau das tut diese Funktion.

    Herauskommt wieder ein Übungsmix ("_p"), der sich abspielen lässt
    wie jeder andere - nur ist der eigene Versuch jetzt darin.

    Drei Dinge müssen dabei stimmen, sonst klingt die neue Datei anders
    als das, was man beim Üben gehört hat:

      1. DIE KANÄLE. Jede Quelle behält die Kanäle, auf denen sie lag.
         Wo sie liegt, steht in ihrem Namen ("Umbrella-1_p" ab Kanal 1,
         "Umbrella-1-Take1_s9" ab Kanal 9) - dieselbe Quelle wie beim
         Üben, nicht eine zweite Wahrheit daneben.

      2. DER VERSATZ. Der Mitschnitt hinkt dem Mix um die Laufzeit
         durch das Pult hinterher (gemessen, siehe
         core/laufzeit_messung.py). Beim Üben wird er deshalb
         vorgezogen; hier muss dasselbe geschehen, sonst wäre die
         Datei um diese Millisekunden verschoben - und das hört man.

      3. DIE LÄNGE. Sie richtet sich nach dem MIX. Ein Mitschnitt, der
         länger ist (die Aufnahme lief nach dem Ende noch weiter),
         würde die Datei sonst verlängern; ein kürzerer wird mit Stille
         aufgefüllt.

    Gelesen wird mit XRacks eigenem W64Reader und nicht über ffmpeg:
    Beide Quellen sind XRacks eigene Wave64-Dateien, und ffmpeg liest
    deren Kopf nicht zuverlässig (es rät pcm_s24le, wo 32-Bit-Behälter
    mit 24 gültigen Bits stehen - siehe writer/w64_writer.py).
    """

    mix = Path(mix)
    take = Path(take)

    for datei in (mix, take):
        if not datei.is_file():
            raise StemCombineError(f"Datei nicht gefunden: {datei.name}")

    mix_leser = W64Reader()
    take_leser = W64Reader()

    try:

        try:
            mix_leser.open(mix)
            take_leser.open(take)

        except Exception as exc:
            raise StemCombineError(
                f"Datei konnte nicht gelesen werden: {exc}"
            ) from exc

        if not mix_leser.channels or not take_leser.channels:
            raise StemCombineError(
                "Mindestens eine Datei hat keine Kanäle - beschädigt?"
            )

        if mix_leser.sample_rate != take_leser.sample_rate:
            #
            # Umrechnen waere moeglich, aber hier falsch: Beide Dateien
            # sind am selben Geraet entstanden. Verschiedene Raten
            # heissen, dass etwas anderes nicht stimmt - und ein
            # stillschweigendes Resampling verdeckte das.
            #
            raise StemCombineError(
                f"Verschiedene Abtastraten: Mix {mix_leser.sample_rate} Hz, "
                f"Mitschnitt {take_leser.sample_rate} Hz."
            )

        rate = mix_leser.sample_rate

        #
        # Wo die beiden liegen (1-basiert aus dem Namen).
        #
        mix_start = start_channel_from_filename(mix.name)
        take_start = start_channel_from_filename(take.name)

        basis = min(mix_start, take_start)

        breite = max(
            mix_start + mix_leser.channels,
            take_start + take_leser.channels,
        ) - basis

        #
        # Der Versatz in Rahmen: So viel FRUEHER wird der Mitschnitt
        # gelesen. Nie negativ - er kann dem Mix nicht vorauseilen
        # (dieselbe Regel wie im UebenDecoder).
        #
        versatz_rahmen = max(0, round(max(0.0, versatz_ms) / 1000.0 * rate))

        if versatz_rahmen:
            take_leser.seek(versatz_rahmen / rate)

        if writer is None:
            writer = W64Writer()

        writer.open(
            channels=breite,
            sample_rate=rate,
            bits_per_sample=24,
            name_prefix=name_prefix,
            marker=MARKER_PRACTICE,
            start_channel=basis,
        )

        quellen = [
            (mix_leser, (mix_start - basis) * BYTES_PER_SAMPLE,
             mix_leser.channels * BYTES_PER_SAMPLE),
            (take_leser, (take_start - basis) * BYTES_PER_SAMPLE,
             take_leser.channels * BYTES_PER_SAMPLE),
        ]

        rahmen_bytes = breite * BYTES_PER_SAMPLE

        while True:

            bloecke = []

            for leser, _, quell_rahmen in quellen:

                roh = leser.read(CHUNK_FRAMES * quell_rahmen) or b""

                bloecke.append(roh)

            #
            # Die Laenge richtet sich nach dem Mix: Ist er zu Ende, ist
            # die Datei zu Ende.
            #
            rahmen = len(bloecke[0]) // quellen[0][2]

            if rahmen <= 0:
                break

            aus = bytearray(rahmen * rahmen_bytes)

            for (leser, ziel_offset, quell_rahmen), block in zip(
                quellen, bloecke
            ):

                #
                # Ein Mitschnitt, der frueher endet, wird ab hier still
                # - aufgefuellt wird durch die Nullen im Zielpuffer.
                #
                vorhanden = min(rahmen, len(block) // quell_rahmen)

                for n in range(vorhanden):

                    ziel = n * rahmen_bytes + ziel_offset
                    quelle = n * quell_rahmen

                    aus[ziel:ziel + quell_rahmen] = (
                        block[quelle:quelle + quell_rahmen]
                    )

            writer.write(bytes(aus))

        dateiname = Path(writer.filename).name

        writer.close()

        return dateiname

    finally:

        mix_leser.close()
        take_leser.close()
