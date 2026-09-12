"""
Prüft core/stem_combiner.py: kombiniert mehrere Stereo-Stems zu einer
Mehrkanal-.w64-Datei über ffmpeg (TrackDecoder) + XRacks echten
W64Writer/W64Reader - ohne ALSA/echte Hardware nötig.
"""

import math
import shutil
import struct
import wave
from pathlib import Path

from core.stem_combiner import combine_stems, StemCombineError
from reader.w64_reader import W64Reader

SCRATCH_DIR = Path("recordings_test_scratch")
RATE = 48000


#
# XRacks Dateien enthalten volle S32_LE-Samples, nicht 24 Bit in
# einem Container - siehe Modul-Docstring von core/stem_combiner.py.
#
FULL_SCALE = 2147483647  # 2^31 - 1


def sample_at(raw: bytes, offset: int) -> int:
    """Liest ein S32_LE-Sample - so, wie ALSA und DAWs es lesen."""

    return struct.unpack_from("<i", raw, offset)[0]


#
# Testwerte laufen bewusst bis dicht an den Vollausschlag, damit die
# Pegelprüfung weiter unten aussagekräftig ist: genau dieser Pegel ging
# verloren, als die Werte fälschlich auf 24 Bit heruntergerechnet
# wurden (Ergebnis war rund 48 dB zu leise).
#
PEAK = int(FULL_SCALE * 0.9)


def expected_samples(frames: int, stem_index: int) -> list[tuple[int, int]]:
    """
    Die erwarteten Sample-Werte (links, rechts) je Frame - bewusst mit
    *beiden Vorzeichen* und nahe Vollausschlag. `stem_index` verschiebt
    die Werte leicht, damit sich die Stems im Ergebnis eindeutig den
    richtigen Kanälen zuordnen lassen.
    """

    result = []

    for i in range(frames):

        magnitude = PEAK - stem_index * 1000 - (i % 100) * 1000

        #
        # Jedes zweite Frame negativ, und der rechte Kanal jeweils
        # entgegengesetzt zum linken - so enthält jeder Kanal beide
        # Vorzeichen.
        #
        sign = 1 if i % 2 == 0 else -1

        left = sign * magnitude
        right = -sign * (magnitude - 500)

        result.append((left, right))

    return result


def write_stereo_wav(path: Path, frames: int, stem_index: int) -> None:
    """
    Erzeugt eine synthetische Stereo-WAV (32-Bit) mit vorhersagbaren
    Werten. Quelle und Ergebnis liegen beide auf S32-Skala, die Werte
    müssen also unverändert durchkommen.
    """

    with wave.open(str(path), "wb") as wav_file:

        wav_file.setnchannels(2)
        wav_file.setsampwidth(4)
        wav_file.setframerate(RATE)

        data = bytearray()

        for left, right in expected_samples(frames, stem_index):

            data += struct.pack("<ii", left, right)

        wav_file.writeframes(bytes(data))


# ----------------------------------------------------------------
# 1. Grundfall: zwei Stems unterschiedlicher Länge -> Stille-Auffüllung
# ----------------------------------------------------------------

SCRATCH_DIR.mkdir(exist_ok=True)

#
# Erzeugte Ausgabedateien mitschreiben, damit sie auch dann wieder
# aufgeräumt werden, wenn der Test unterwegs fehlschlägt - sonst
# bleiben sie in recordings/ liegen und tauchen in der App auf.
#
created_files: list[Path] = []

try:

    long_frames = 4800   # 0.1s bei 48kHz
    short_frames = 2400  # 0.05s bei 48kHz

    stem1 = SCRATCH_DIR / "stem1.wav"
    stem2 = SCRATCH_DIR / "stem2.wav"

    write_stereo_wav(stem1, long_frames, stem_index=0)
    write_stereo_wav(stem2, short_frames, stem_index=1)

    filename = combine_stems(
        [stem1, stem2],
        target_rate=RATE,
        name_prefix="ÜbungsmixTest",
    )

    output_path = Path("recordings") / filename

    created_files.append(output_path)

    assert output_path.exists(), "Ausgabedatei wurde nicht angelegt."

    reader = W64Reader()
    reader.open(output_path)

    assert reader.channels == 4, f"Erwartet 4 Kanäle, bekommen {reader.channels}"
    assert reader.sample_rate == RATE, f"Erwartet {RATE} Hz, bekommen {reader.sample_rate}"
    assert reader.bits_per_sample == 24, f"Erwartet 24 Bit, bekommen {reader.bits_per_sample}"

    raw = b""
    while True:
        chunk = reader.read(65536)
        if chunk is None:
            break
        raw += chunk

    reader.close()

    bytes_per_frame = 4 * 4  # 4 Kanäle * 4 Byte pro S32-Sample
    frame_count = len(raw) // bytes_per_frame

    assert frame_count == long_frames, (
        f"Erwartet {long_frames} Frames (Länge des längsten Stems), "
        f"bekommen {frame_count}"
    )

    expected_long = expected_samples(long_frames, stem_index=0)
    expected_short = expected_samples(short_frames, stem_index=1)

    mismatches = 0

    for i in range(frame_count):

        frame_offset = i * bytes_per_frame

        ch1 = sample_at(raw, frame_offset + 0)
        ch2 = sample_at(raw, frame_offset + 4)
        ch3 = sample_at(raw, frame_offset + 8)
        ch4 = sample_at(raw, frame_offset + 12)

        if (ch1, ch2) != expected_long[i]:
            mismatches += 1

        if i < short_frames:
            if (ch3, ch4) != expected_short[i]:
                mismatches += 1
        else:
            if ch3 != 0 or ch4 != 0:
                mismatches += 1

    assert mismatches == 0, f"{mismatches} Frame(s) weichen vom Erwartungswert ab."

    print("OK: Zwei Stems korrekt zu 4-Kanal-.w64 kombiniert, kürzerer Stem mit Stille aufgefüllt")

    # ----------------------------------------------------------------
    # 1b. Pegel muss erhalten bleiben
    #
    # Die Prüfung oben vergleicht zwar sample-genau, würde eine
    # gleichmäßige Abschwächung aller Werte aber nur dann bemerken,
    # wenn die Erwartungswerte selbst auf der richtigen Skala liegen.
    # Darum hier zusätzlich explizit gegen den Vollausschlag prüfen:
    # eine frühere Fassung rechnete die Samples auf 24 Bit herunter
    # (`value >> 8`), wodurch der Übungsmix rund 48 dB zu leise war,
    # obwohl er ansonsten völlig korrekt klang.
    # ----------------------------------------------------------------

    negative_seen = 0
    peak = 0

    for i in range(frame_count):

        frame_offset = i * bytes_per_frame

        for channel in range(4):

            value = sample_at(raw, frame_offset + channel * 4)

            if value < 0:
                negative_seen += 1

            peak = max(peak, abs(value))

    assert negative_seen > 0, (
        "Testdaten enthalten keine negativen Samples - die "
        "Vorzeichenprüfung wäre wirkungslos."
    )

    assert peak == PEAK, (
        f"Spitzenwert {peak} statt {PEAK} - der Pegel stimmt nicht "
        f"(Faktor {PEAK / peak:.1f}, entspricht "
        f"{20 * math.log10(peak / PEAK):.1f} dB)."
    )

    print(
        f"OK: Pegel bleibt erhalten (Spitzenwert {peak} = "
        f"{peak / FULL_SCALE:.1%} von Vollausschlag, "
        f"{negative_seen} negative Samples geprüft)"
    )

    # ----------------------------------------------------------------
    # 2. Zu wenige Dateien
    # ----------------------------------------------------------------

    try:
        combine_stems([stem1], target_rate=RATE, name_prefix="Fail")
        raise AssertionError("Erwartete StemCombineError bei nur 1 Datei.")
    except StemCombineError:
        print("OK: Weniger als 2 Dateien wird abgelehnt")

    # ----------------------------------------------------------------
    # 3. Zu viele Dateien
    # ----------------------------------------------------------------

    too_many = [stem1] * 9

    try:
        combine_stems(too_many, target_rate=RATE, name_prefix="Fail")
        raise AssertionError("Erwartete StemCombineError bei 9 Dateien.")
    except StemCombineError:
        print("OK: Mehr als 8 Dateien wird abgelehnt")

    # ----------------------------------------------------------------
    # 4. Der erste Kanal wandert in den Dateinamen
    #
    # Ein Übungsmix wird für einen Platz im Pult gebaut: Vier Stems ab
    # Kanal 9 gehören beim nächsten Üben wieder auf 9. Die Angabe
    # reist im Namen mit - über USB, Download und Backup -, statt in
    # einer Verwaltungsdatei zu stehen, die niemand mitkopiert
    # (ausführlich in core/recording_kind.py).
    #
    # Geprüft wird auch das Gegenstück: dass der Name rückwärts wieder
    # denselben Kanal ergibt. Genau dort ginge er sonst verloren.
    # ----------------------------------------------------------------

    from core.recording_kind import (  # noqa: E402
        KIND_PRACTICE,
        kind_from_filename,
        start_channel_from_filename,
    )

    ab_neun = combine_stems(
        [stem1, stem2],
        target_rate=RATE,
        name_prefix="AbKanalNeun",
        start_channel=9,
    )

    created_files.append(Path("recordings") / ab_neun)

    assert start_channel_from_filename(ab_neun) == 9, (
        f"Aus {ab_neun!r} liest XRack Kanal "
        f"{start_channel_from_filename(ab_neun)} statt 9 - der Mix "
        f"landete beim Üben wieder auf Kanal 1, ohne Fehlermeldung."
    )

    assert kind_from_filename(ab_neun) == KIND_PRACTICE, (
        f"{ab_neun!r} gilt nicht mehr als Übungsmix - mit der Ziffer "
        f"im Kürzel darf die Art nicht verlorengehen."
    )

    #
    # Und ohne Angabe bleibt alles, wie es war: Jeder bisher erstellte
    # Übungsmix heisst so und gehört auf Kanal 1.
    #
    assert start_channel_from_filename(filename) == 1, (
        f"{filename!r} meint plötzlich Kanal "
        f"{start_channel_from_filename(filename)} - ohne Angabe ist es "
        f"Kanal 1, sonst wären alle alten Mixe verschoben."
    )

    print("OK: Der erste Kanal steht im Namen und lässt sich zurücklesen")

    # ----------------------------------------------------------------
    # 5. Was nicht auf das Interface passt, wird vorher abgelehnt
    #
    # Gemessen ab dem ersten Kanal, nicht ab 1: Vier Stems ab Kanal 13
    # brauchen bis Kanal 20. Was darüber hinausragt, wäre beim Üben
    # still - und warum, sähe niemand.
    #
    # Und nur ungerade Startkanäle: Jeder Stem ist ein Stereopaar; ab
    # einem geraden Kanal läge jedes Paar quer über zwei Paare des
    # Pults, links und rechts kämen aus verschiedenen Zügen.
    # ----------------------------------------------------------------

    import threading  # noqa: E402
    import time  # noqa: E402

    from core.application.aufnahme import AufnahmeMixin  # noqa: E402

    class Interface:
        def __init__(self, channels):
            self.channels = channels

    class Prueflauf(AufnahmeMixin):
        """Nur die Annahme prüfen - gerechnet wird hier nichts."""

        def __init__(self, channels):
            self.selected_audio_device = Interface(channels)
            self.mixer_sample_rate = RATE
            self._stem_combine_lock = threading.Lock()
            self.stem_combine_state = {"active": False}
            self.gestartet = []

        def _run_stem_combine(self, name, file_paths, start_channel=1):
            self.gestartet.append((name, len(file_paths), start_channel))

    faelle = (
        (18, 1, 4, True,  "vier Stems ab Kanal 1 auf einem 18er"),
        (18, 11, 4, True, "vier Stems ab Kanal 11 - passt bis 18"),
        (18, 13, 4, False, "vier Stems ab Kanal 13 - reicht bis 20"),
        (18, 2, 2, False, "gerader Startkanal"),
        (18, 0, 2, False, "Kanal 0 gibt es nicht"),
    )

    for kanaele, start, stems, erlaubt, beschreibung in faelle:

        lauf = Prueflauf(kanaele)

        erfolg, meldung = lauf.start_stem_combine(
            "Prüfung",
            [stem1] * stems,
            start,
        )

        assert erfolg is erlaubt, (
            f"{beschreibung}: {'abgelehnt' if erlaubt else 'angenommen'} "
            f"({meldung!r})"
        )

        if erlaubt:
            #
            # Der Kanal muss auch wirklich weitergereicht werden - er
            # ist es, der gleich im Dateinamen landet. Die Arbeit läuft
            # in einem eigenen Faden, also warten statt schlafen.
            #
            frist = time.monotonic() + 5

            while not lauf.gestartet and time.monotonic() < frist:
                time.sleep(0.01)

            assert lauf.gestartet == [("Prüfung", stems, start)], (
                f"{beschreibung}: weitergereicht wurde "
                f"{lauf.gestartet}"
            )
        else:
            assert meldung, f"{beschreibung}: Ablehnung ohne Begründung."

    print("OK: Der Kanalbereich wird geprüft, bevor etwas geschrieben wird")

    print("Alle Tests erfolgreich.")

finally:

    shutil.rmtree(SCRATCH_DIR, ignore_errors=True)

    for path in created_files:
        path.unlink(missing_ok=True)
