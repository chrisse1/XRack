"""
Pegelmessung (Peak-Meter) für PCM-Audiodaten.
"""

import struct


class LevelMeter:
    """
    Berechnet Peak-Pegel je Kanal aus S32_LE-Rohdaten
    (volle 32 Bit pro Sample, siehe AudioBackend).

    Die Anzahl der Kanäle ergibt sich aus der aktuell gewählten
    Aufnahmekanalzahl - die Anzeige passt sich also automatisch an,
    egal ob am Interface 18 (XR18) oder z.B. 32 Kanäle (X32)
    gewählt wurden.

    Hinweis zum Format: AudioBackend fordert PCM_FORMAT_S24_LE an,
    wertet den Rückgabewert von setformat() aber nicht aus - die
    X-Serie bietet dieses Format über USB offenbar nicht an, sodass
    ALSA tatsächlich S32_LE liefert. Diese Anzeige rechnete früher
    mit 24-Bit-Vollausschlag und maskierte auf die unteren 24 Bit;
    bei 32-Bit-Daten sind das die untersten, quasi zufälligen Bits,
    weshalb die Anzeige schon bei leisem Signal fast voll ausschlug.
    """

    BYTES_PER_SAMPLE = 4

    #
    # 32-Bit-Vollausschlag (2^31 - 1)
    #
    FULL_SCALE = 2147483647

    def __init__(self, channels: int, decay: float = 0.7):

        self.channels = channels

        self.decay = decay

        self.levels = [0.0] * channels

    def update(self, data: bytes) -> list[float]:
        """
        Wertet einen neuen Datenblock aus und aktualisiert die
        Pegel (mit Abklingen, damit die Anzeige nicht flackert).
        """

        peaks = self._compute_peaks(data)

        self.levels = [
            max(peak, level * self.decay)
            for peak, level in zip(peaks, self.levels)
        ]

        return self.levels

    def _compute_peaks(self, data: bytes) -> list[float]:
        """
        Ermittelt den maximalen Pegel je Kanal in einem Datenblock
        (0.0 - 1.0+, >1.0 bedeutet Übersteuerung).
        """

        frame_size = self.channels * self.BYTES_PER_SAMPLE

        frame_count = len(data) // frame_size

        if frame_count == 0:
            return [0.0] * self.channels

        sample_count = frame_count * self.channels

        #
        # Alle Samples in einem Rutsch als vorzeichenbehaftete
        # 32-Bit-Werte lesen (schneller als Byte-für-Byte in Python) -
        # struct erledigt die Vorzeichenbehandlung dabei selbst.
        #
        values = struct.unpack(
            f"<{sample_count}i",
            data[:sample_count * self.BYTES_PER_SAMPLE],
        )

        peaks = [0] * self.channels

        index = 0

        for _ in range(frame_count):

            for channel in range(self.channels):

                value = values[index]

                magnitude = value if value >= 0 else -value

                if magnitude > peaks[channel]:
                    peaks[channel] = magnitude

                index += 1

        return [
            peak / self.FULL_SCALE
            for peak in peaks
        ]
