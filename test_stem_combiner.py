"""
Prüft core/stem_combiner.py: kombiniert mehrere Stereo-Stems zu einer
Mehrkanal-.w64-Datei über ffmpeg (TrackDecoder) + XRacks echten
W64Writer/W64Reader - ohne ALSA/echte Hardware nötig.
"""

import shutil
import struct
import wave
from pathlib import Path

from core.stem_combiner import combine_stems, StemCombineError
from reader.w64_reader import W64Reader

SCRATCH_DIR = Path("recordings_test_scratch")
RATE = 48000


def sample_from_container(raw: bytes, offset: int) -> int:
    """Wie player/player.py: 24-Bit-Wert aus 4-Byte-Container extrahieren."""

    value = struct.unpack_from("<I", raw, offset)[0] & 0xFFFFFF

    if value & 0x800000:
        value -= 0x1000000

    return value


def expected_samples(frames: int, base_value: int) -> list[tuple[int, int]]:
    """
    Die erwarteten 24-Bit-Werte (links, rechts) je Frame - bewusst mit
    *beiden Vorzeichen* und nahe Vollausschlag, damit ein falsch
    gefülltes oberstes Container-Byte auffällt (siehe unten).
    """

    result = []

    for i in range(frames):

        magnitude = base_value + i

        #
        # Jedes zweite Frame negativ, und der rechte Kanal jeweils
        # entgegengesetzt zum linken - so enthält jeder Kanal beide
        # Vorzeichen.
        #
        sign = 1 if i % 2 == 0 else -1

        left = sign * magnitude
        right = -sign * (magnitude + 1000)

        result.append((left, right))

    return result


def write_stereo_wav(path: Path, frames: int, base_value: int) -> None:
    """
    Erzeugt eine synthetische Stereo-WAV (32-Bit) mit vorhersagbaren
    Werten - die unteren 8 Bit bewusst 0, damit die S32->S24-Container-
    Konvertierung (`value >> 8`) verlustfrei rückgängig gemacht werden
    kann (kein Runden/Abschneiden bei der Prüfung nötig).
    """

    with wave.open(str(path), "wb") as wav_file:

        wav_file.setnchannels(2)
        wav_file.setsampwidth(4)
        wav_file.setframerate(RATE)

        data = bytearray()

        for left, right in expected_samples(frames, base_value):

            data += struct.pack("<ii", left << 8, right << 8)

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

    write_stereo_wav(stem1, long_frames, base_value=100)
    write_stereo_wav(stem2, short_frames, base_value=5000)

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

    bytes_per_frame = 4 * 4  # 4 Kanäle * 4-Byte-Container
    frame_count = len(raw) // bytes_per_frame

    assert frame_count == long_frames, (
        f"Erwartet {long_frames} Frames (Länge des längsten Stems), "
        f"bekommen {frame_count}"
    )

    expected_long = expected_samples(long_frames, base_value=100)
    expected_short = expected_samples(short_frames, base_value=5000)

    mismatches = 0

    for i in range(frame_count):

        frame_offset = i * bytes_per_frame

        ch1 = sample_from_container(raw, frame_offset + 0)
        ch2 = sample_from_container(raw, frame_offset + 4)
        ch3 = sample_from_container(raw, frame_offset + 8)
        ch4 = sample_from_container(raw, frame_offset + 12)

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
    # 1b. Oberstes Container-Byte muss vorzeichenrichtig gefüllt sein
    #
    # XRacks eigener Reader maskiert das oberste Byte weg (& 0xFFFFFF),
    # die Prüfung oben würde einen Fehler dort also gar nicht sehen.
    # DAWs und der ALSA-Wiedergabeweg lesen das 4-Byte-Wort aber als
    # vorzeichenbehaftete 32-Bit-Zahl (der Header deklariert
    # wBitsPerSample = 32) - ein genulltes oberstes Byte macht daraus
    # bei negativen Samples eine große positive Zahl und die Wiedergabe
    # klingt stark verzerrt. Genau das war der Fehler in der ersten
    # Fassung, darum hier explizit auf Byte-Ebene prüfen.
    # ----------------------------------------------------------------

    negative_seen = 0
    byte_mismatches = 0
    signed_mismatches = 0

    for i in range(frame_count):

        frame_offset = i * bytes_per_frame

        for channel in range(4):

            offset = frame_offset + channel * 4

            value24 = sample_from_container(raw, offset)

            top_byte = raw[offset + 3]

            expected_top = 0xFF if value24 < 0 else 0x00

            if top_byte != expected_top:
                byte_mismatches += 1

            #
            # Gegenprobe: so, wie DAW und ALSA das Wort lesen.
            #
            as_signed_32 = struct.unpack_from("<i", raw, offset)[0]

            if as_signed_32 != value24:
                signed_mismatches += 1

            if value24 < 0:
                negative_seen += 1

    assert negative_seen > 0, (
        "Testdaten enthalten keine negativen Samples - die "
        "Vorzeichenprüfung wäre wirkungslos."
    )

    assert byte_mismatches == 0, (
        f"{byte_mismatches} Sample(s) mit falsch gefülltem obersten "
        f"Container-Byte."
    )

    assert signed_mismatches == 0, (
        f"{signed_mismatches} Sample(s) werden als vorzeichenbehaftete "
        f"32-Bit-Zahl falsch gelesen (so lesen DAWs und ALSA die Datei)."
    )

    print(
        f"OK: Oberstes Container-Byte vorzeichenrichtig gefüllt "
        f"({negative_seen} negative Samples geprüft)"
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

    print("Alle Tests erfolgreich.")

finally:

    shutil.rmtree(SCRATCH_DIR, ignore_errors=True)

    for path in created_files:
        path.unlink(missing_ok=True)
