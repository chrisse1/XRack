"""
Erkennt eine Abweichung zwischen der konfigurierten (Soll-)Samplerate
und der über blockierende ALSA-read()-Aufrufe gemessenen Ist-Rate der
tatsächlichen Hardware-Clock (siehe Application.check_sample_rate()).
"""

from time import monotonic

from core.configuration import ALLOWED_SAMPLE_RATES


class SampleRateMonitor:
    """
    Vergleicht "wie viele Frames sind seit Fensterbeginn tatsächlich
    durchgelaufen" mit der seitdem verstrichenen Wanduhrzeit. Da
    read() blockierend ist und sich nach der echten Hardware-Clock
    taktet, ergibt sich daraus eine von der konfigurierten Rate
    unabhängige Ist-Messung.
    """

    WINDOW_SECONDS = 5.0
    MISMATCH_RATIO_THRESHOLD = 0.04

    def __init__(self, candidate_rates=ALLOWED_SAMPLE_RATES):

        self._candidate_rates = candidate_rates

        self._target_rate = 0

        self._window_start: float | None = None
        self._window_frames = 0

        self._mismatch = False
        self._measured_rate = 0
        self._suggested_rate = 0

    def reset(self, target_rate: int) -> None:
        """
        Bei jedem open()/close() aufrufen (close() mit target_rate=0).
        Startet ein neues Messfenster, verwirft alte Messwerte.
        """

        self._target_rate = target_rate
        self._window_start = None
        self._window_frames = 0
        self._mismatch = False
        self._measured_rate = 0
        self._suggested_rate = 0

    def record(self, frames: int) -> None:
        """
        Nach jedem erfolgreichen read() mit der Anzahl transferierter
        Frames aufrufen.
        """

        if frames <= 0 or self._target_rate <= 0:
            return

        now = monotonic()

        if self._window_start is None:
            #
            # Erster Aufruf nach reset() - nur Startzeitpunkt merken,
            # damit die Öffnungslatenz nicht in die Messung einfließt.
            #
            self._window_start = now
            self._window_frames = 0
            return

        self._window_frames += frames

        elapsed = now - self._window_start

        if elapsed < self.WINDOW_SECONDS:
            return

        measured_rate = self._window_frames / elapsed

        self._measured_rate = round(measured_rate)

        deviation = abs(measured_rate - self._target_rate) / self._target_rate

        self._mismatch = deviation > self.MISMATCH_RATIO_THRESHOLD

        self._suggested_rate = min(
            self._candidate_rates,
            key=lambda rate: abs(rate - measured_rate),
        )

        #
        # Neues Fenster - altes Material fließt nicht in die nächste
        # Auswertung ein.
        #
        self._window_start = now
        self._window_frames = 0

    @property
    def mismatch(self) -> bool:
        return self._mismatch

    @property
    def measured_rate(self) -> int:
        return self._measured_rate

    @property
    def suggested_rate(self) -> int:
        return self._suggested_rate
