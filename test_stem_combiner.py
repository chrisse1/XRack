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


def write_stereo_wav(path: Path, frames: int, base_value: int) -> None:
    """
    Erzeugt eine synthetische Stereo-WAV (32-Bit) mit vorhersagbaren
    Werten - niedrigstes Byte bewusst 0, damit die S32->S24-Container-
    Konvertierung (`value >> 8`) verlustfrei rückgängig gemacht werden
    kann (kein Runden/Abschneiden bei der Prüfung nötig).
    """

    with wave.open(str(path), "wb") as wav_file:

        wav_file.setnchannels(2)
        wav_file.setsampwidth(4)
        wav_file.setframerate(RATE)

        data = bytearray()

        for i in range(frames):

            left = (base_value + i) << 8
            right = (base_value + i + 1000) << 8

            data += struct.pack("<ii", left, right)

        wav_file.writeframes(bytes(data))


# ----------------------------------------------------------------
# 1. Grundfall: zwei Stems unterschiedlicher Länge -> Stille-Auffüllung
# ----------------------------------------------------------------

SCRATCH_DIR.mkdir(exist_ok=True)

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

    mismatches = 0

    for i in range(frame_count):

        frame_offset = i * bytes_per_frame

        ch1 = sample_from_container(raw, frame_offset + 0)
        ch2 = sample_from_container(raw, frame_offset + 4)
        ch3 = sample_from_container(raw, frame_offset + 8)
        ch4 = sample_from_container(raw, frame_offset + 12)

        if ch1 != 100 + i or ch2 != 100 + i + 1000:
            mismatches += 1

        if i < short_frames:
            if ch3 != 5000 + i or ch4 != 5000 + i + 1000:
                mismatches += 1
        else:
            if ch3 != 0 or ch4 != 0:
                mismatches += 1

    assert mismatches == 0, f"{mismatches} Frame(s) weichen vom Erwartungswert ab."

    print("OK: Zwei Stems korrekt zu 4-Kanal-.w64 kombiniert, kürzerer Stem mit Stille aufgefüllt")

    output_path.unlink()

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
