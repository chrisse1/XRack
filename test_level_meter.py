"""
Prüft LevelMeter: korrekte Vorzeichenbehandlung von S32_LE-Samples,
Mehrkanal-Interleaving und Abklingen.

Hinweis: Die Anzeige rechnete früher mit 24-Bit-Vollausschlag und
maskierte auf die unteren 24 Bit. AudioBackend fordert zwar
PCM_FORMAT_S24_LE an, bekommt von ALSA aber tatsächlich S32_LE
geliefert - dadurch wertete die Anzeige die untersten, quasi
zufälligen Bits aus und schlug schon bei leisem Signal fast voll aus.
"""

import struct

from recorder.level_meter import LevelMeter


def make_sample(value: int) -> bytes:
    """Baut ein einzelnes S32_LE-Sample."""

    return struct.pack("<i", value)


FULL_SCALE = 2147483647  # 2^31 - 1

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
levels = meter.update(make_sample(-2147483648))
assert levels[0] > 1.0, f"Negativer Vollausschlag sollte >1.0 ergeben, nicht {levels[0]}"
print(f"OK: Negativer Vollausschlag -> Pegel {levels[0]:.4f} (>1.0, wie erwartet)")

meter = LevelMeter(channels=1, decay=0.0)
levels = meter.update(make_sample(-1073741824))
assert abs(levels[0] - 0.5) < 1e-6, f"Negativer Halbausschlag sollte ~0.5 ergeben, nicht {levels[0]}"
print("OK: Negativer Halbausschlag -> Pegel ~0.5 (Vorzeichen korrekt erkannt)")

# ----------------------------------------------------------------
# 2. Ein leises Signal darf NICHT fast voll ausschlagen
#
# Genau das war der Fehler: die Anzeige maskierte auf die unteren
# 24 Bit und rechnete mit 24-Bit-Vollausschlag. Bei S32_LE-Daten
# sind das die untersten, quasi zufälligen Bits - ein Signal bei
# -48 dB schlug dadurch voll aus.
# ----------------------------------------------------------------

quiet_value = FULL_SCALE // 256  # rund -48 dB

meter = LevelMeter(channels=1, decay=0.0)
levels = meter.update(make_sample(quiet_value))

assert abs(levels[0] - 1.0 / 256) < 1e-4, (
    f"Ein Signal bei rund -48 dB sollte einen Pegel um "
    f"{1.0 / 256:.5f} ergeben, nicht {levels[0]:.5f}."
)
print(f"OK: Leises Signal (-48 dB) -> Pegel {levels[0]:.5f} (schlägt nicht voll aus)")

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
