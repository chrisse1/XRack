"""
Prüft die Samplerate-Mismatch-Erkennung isoliert (ohne ALSA/echte
Hardware) - simuliert per Fake-Uhr, wie viele Frames "in welcher Zeit"
angekommen wären, und prüft, dass ein echter Mismatch (~8-9% Abweichung
bei 44,1 vs. 48 kHz) zuverlässig erkannt wird, ein Match dagegen nicht,
und dass zu wenig verstrichene Zeit noch keinen Fehlalarm auslöst.
"""

import audio.sample_rate_monitor as sample_rate_monitor_module
from audio.sample_rate_monitor import SampleRateMonitor

PERIOD_FRAMES = 1024


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


fake_clock = FakeClock()
sample_rate_monitor_module.monotonic = fake_clock


def feed(monitor: SampleRateMonitor, real_rate: int, seconds: float) -> None:
    """
    Simuliert `seconds` Sekunden realen Audiodurchsatz bei `real_rate`
    Frames/Sekunde, in PERIOD_FRAMES-Schritten (wie AudioBackend.read()
    es bei einer Periodengröße von 1024 tun würde).
    """

    period_duration = PERIOD_FRAMES / real_rate

    elapsed = 0.0

    while elapsed < seconds:
        fake_clock.advance(period_duration)
        monitor.record(PERIOD_FRAMES)
        elapsed += period_duration


# ----------------------------------------------------------------
# 1. Match-Fall: reale Rate entspricht der konfigurierten Rate
# ----------------------------------------------------------------

monitor = SampleRateMonitor()
monitor.reset(48000)

feed(monitor, real_rate=48000, seconds=SampleRateMonitor.WINDOW_SECONDS + 1)

assert monitor.mismatch is False, "Match wurde faelschlich als Mismatch erkannt."
assert 47000 <= monitor.measured_rate <= 49000, monitor.measured_rate
print("OK: Match-Fall erkennt keinen Mismatch")

# ----------------------------------------------------------------
# 2. Mismatch-Fall: Konsole läuft real bei 44100, konfiguriert 48000
# ----------------------------------------------------------------

monitor = SampleRateMonitor()
monitor.reset(48000)

feed(monitor, real_rate=44100, seconds=SampleRateMonitor.WINDOW_SECONDS + 1)

assert monitor.mismatch is True, "Echter 44,1/48-kHz-Mismatch wurde nicht erkannt."
assert monitor.suggested_rate == 44100, monitor.suggested_rate
print("OK: Mismatch-Fall (44100 real vs. 48000 konfiguriert) korrekt erkannt")

# ----------------------------------------------------------------
# 3. Fenster-Schutz: gleiche Abweichung, aber noch nicht genug Zeit
# ----------------------------------------------------------------

monitor = SampleRateMonitor()
monitor.reset(48000)

feed(monitor, real_rate=44100, seconds=SampleRateMonitor.WINDOW_SECONDS - 1)

assert monitor.mismatch is False, (
    "Vor Ablauf des Messfensters darf noch kein Mismatch gemeldet werden."
)
print("OK: Kein Fehlalarm vor Abschluss des ersten Fensters")

# ----------------------------------------------------------------
# 4. Reset bei Reopen: alte Messwerte duerfen nicht uebernommen werden
# ----------------------------------------------------------------

monitor = SampleRateMonitor()
monitor.reset(48000)
feed(monitor, real_rate=44100, seconds=SampleRateMonitor.WINDOW_SECONDS + 1)
assert monitor.mismatch is True

monitor.reset(96000)

assert monitor.mismatch is False, "reset() hat den alten Mismatch nicht zurueckgesetzt."
assert monitor.measured_rate == 0
print("OK: reset() verwirft alte Messwerte")

print("Alle Tests erfolgreich.")
