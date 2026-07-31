"""
Prüft LevelMeter: korrekte Vorzeichenbehandlung von 24-Bit-Werten
in einem 4-Byte-Container, Mehrkanal-Interleaving und Abklingen.
"""

from recorder.level_meter import LevelMeter


def make_sample(value: int, junk_top_byte: int = 0x00) -> bytes:
    """
    Baut ein einzelnes 4-Byte-Sample aus einem 24-Bit-Zweierkomplement-
    Wert. `junk_top_byte` simuliert, dass das oberste (vierte) Byte
    laut ALSA-Spezifikation undefiniert ist - es darf das Ergebnis
    nicht beeinflussen.
    """

    if value < 0:
        value += 0x1000000

    return bytes([
        value & 0xFF,
        (value >> 8) & 0xFF,
        (value >> 16) & 0xFF,
        junk_top_byte,
    ])


FULL_SCALE = 8388607  # 2^23 - 1

# ----------------------------------------------------------------
# 1. Grundwerte: 0, positiver/negativer Vollausschlag, halber Pegel
# ----------------------------------------------------------------

meter = LevelMeter(channels=1, decay=0.0)

levels = meter.update(make_sample(0))
assert levels[0] == 0.0, f"Stille sollte 0.0 ergeben, nicht {levels[0]}"
print("OK: Stille -> Pegel 0.0")

meter = LevelMeter(channels=1, decay=0.0)
levels = meter.update(make_sample(FULL_SCALE))
assert abs(levels[0] - 1.0) < 1e-9, f"Positiver Vollausschlag sollte 1.0 ergeben, nicht {levels[0]}"
print("OK: Positiver Vollausschlag -> Pegel 1.0")

meter = LevelMeter(channels=1, decay=0.0)
levels = meter.update(make_sample(-8388608))
assert levels[0] > 1.0, f"Negativer Vollausschlag sollte >1.0 ergeben, nicht {levels[0]}"
print(f"OK: Negativer Vollausschlag -> Pegel {levels[0]:.4f} (>1.0, wie erwartet)")

meter = LevelMeter(channels=1, decay=0.0)
levels = meter.update(make_sample(-4194304))
assert abs(levels[0] - 0.5) < 1e-6, f"Negativer Halbausschlag sollte ~0.5 ergeben, nicht {levels[0]}"
print("OK: Negativer Halbausschlag -> Pegel ~0.5 (Vorzeichen korrekt erkannt)")

# ----------------------------------------------------------------
# 2. Das oberste (undefinierte) Byte darf keinen Einfluss haben
# ----------------------------------------------------------------

meter = LevelMeter(channels=1, decay=0.0)
levels_clean = meter.update(make_sample(4194304, junk_top_byte=0x00))

meter = LevelMeter(channels=1, decay=0.0)
levels_junk = meter.update(make_sample(4194304, junk_top_byte=0xFF))

assert levels_clean == levels_junk, (
    "Das oberste Byte beeinflusst das Ergebnis, sollte es aber nicht "
    "(laut ALSA-Spezifikation undefiniert)."
)
print("OK: Undefiniertes oberstes Byte wird korrekt ignoriert")

# ----------------------------------------------------------------
# 3. Mehrkanal-Interleaving: Pegel pro Kanal bleiben getrennt
# ----------------------------------------------------------------

meter = LevelMeter(channels=2, decay=0.0)

frame1 = make_sample(FULL_SCALE) + make_sample(0)      # Kanal 0 laut, Kanal 1 still
frame2 = make_sample(0) + make_sample(FULL_SCALE)       # Kanal 0 still, Kanal 1 laut

levels = meter.update(frame1 + frame2)

assert abs(levels[0] - 1.0) < 1e-9, f"Kanal 0 sollte 1.0 sein, ist {levels[0]}"
assert abs(levels[1] - 1.0) < 1e-9, f"Kanal 1 sollte 1.0 sein, ist {levels[1]}"
print("OK: Kanäle werden unabhängig voneinander ausgewertet (kein Übersprechen)")

# ----------------------------------------------------------------
# 4. Kanalzahl passt sich an (z.B. 8 statt 18/32)
# ----------------------------------------------------------------

for channels in (2, 8, 18, 32):
    meter = LevelMeter(channels=channels, decay=0.0)
    frame = b"".join(make_sample(FULL_SCALE) for _ in range(channels))
    levels = meter.update(frame)
    assert len(levels) == channels
    assert all(abs(level - 1.0) < 1e-9 for level in levels)

print("OK: Pegelanzeige skaliert korrekt mit der gewählten Kanalzahl (2/8/18/32)")

# ----------------------------------------------------------------
# 5. Abklingverhalten (Decay) - kein sofortiger Rückfall auf 0
# ----------------------------------------------------------------

meter = LevelMeter(channels=1, decay=0.7)

loud = meter.update(make_sample(FULL_SCALE))
assert abs(loud[0] - 1.0) < 1e-9

silence = meter.update(make_sample(0))
assert abs(silence[0] - 0.7) < 1e-9, (
    f"Nach einem Block Stille sollte der Pegel um den Decay-Faktor "
    f"abklingen (0.7), ist aber {silence[0]}"
)
print("OK: Pegel klingt nach Stille geglättet ab, statt sofort auf 0 zu springen")

still_silence = meter.update(make_sample(0))
assert abs(still_silence[0] - 0.49) < 1e-6
print("OK: Abklingen setzt sich über mehrere Blöcke fort (0.7 * 0.7 = 0.49)")

print("Alle Tests erfolgreich.")
