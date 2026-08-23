"""
Low-Level Zugriff auf das Audio-Interface.

Diese Klasse kapselt den direkten Zugriff auf ALSA.
"""

import logging

import alsaaudio

from audio.channel_extractor import ChannelExtractor
from audio.models import AudioDevice, DiagnosticItem
from audio.sample_rate_monitor import SampleRateMonitor


class AudioBackend:
    """Kommuniziert direkt mit ALSA."""

    def __init__(self):

        self.logger = logging.getLogger("XRack")

        self.device: AudioDevice | None = None

        self._pcm = None

        self._rate = 0
        self._channels = 0
        self._native_channels = 0
        self._period_size = 0
        self._format = None
        self._extractor: ChannelExtractor | None = None
        self._rate_monitor = SampleRateMonitor()

    # ---------------------------------------------------------
    # Properties
    # ---------------------------------------------------------

    @property
    def opened(self) -> bool:
        """True, wenn ein PCM-Handle geöffnet ist."""
        return self._pcm is not None

    @property
    def rate(self) -> int:
        return self._rate

    @property
    def channels(self) -> int:
        return self._channels

    @property
    def period_size(self) -> int:
        return self._period_size

    @property
    def sample_format(self):
        return self._format

    @property
    def rate_mismatch(self) -> bool:
        """
        True, wenn die gemessene Ist-Rate signifikant von der
        konfigurierten Samplerate abweicht (siehe SampleRateMonitor).
        """
        return self._rate_monitor.mismatch

    @property
    def measured_rate(self) -> int:
        return self._rate_monitor.measured_rate

    @property
    def suggested_rate(self) -> int:
        return self._rate_monitor.suggested_rate

    @property
    def alsa_name(self) -> str:
        """Liefert den ALSA-Gerätenamen."""

        if self.device is None:
            return ""

        return f"hw:{self.device.card},{self.device.device}"

    # ---------------------------------------------------------
    # Öffnen / Schließen
    # ---------------------------------------------------------

    def open(
        self,
        device: AudioDevice,
        channels: int | None = None,
        rate: int | None = None,
    ) -> bool:
        """
        Öffnet das Audiogerät.

        Das Interface wird IMMER mit seiner vollen, festen
        Kanalzahl (device.channels) geöffnet. Digitalmischpulte wie
        die Behringer X-Serie kennen über USB keinen Modus mit
        weniger Kanälen - fordert man dort z.B. 8 statt 18 Kanäle
        an, nimmt ALSA trotzdem alle 18 auf, meldet aber keinen
        Fehler. Ohne diese Regel verschieben sich dadurch alle
        Kanäle im Datenstrom (falsche Spur, falsche Dauer).

        Die gewünschte (kleinere) Kanalzahl wird stattdessen erst
        beim Lesen in Software aus dem Datenstrom herausgeschnitten,
        siehe `audio.channel_extractor.ChannelExtractor`.

        `rate` ist die vom Nutzer erklärte, tatsächlich am Interface
        eingestellte Samplerate (siehe
        `Application.set_mixer_sample_rate()`) - `device.sample_rate`
        selbst ist nur der von ALSA gemeldete Wertebereich und kein
        verlässlicher Hinweis auf die tatsächlich aktive Clock.
        """

        self.device = device

        self._rate = rate if rate is not None else device.sample_rate
        self._rate_monitor.reset(self._rate)
        self._native_channels = device.channels
        self._channels = (
            channels
            if channels is not None
            else device.channels
        )
        self._period_size = 1024

        self._format = alsaaudio.PCM_FORMAT_S24_LE

        self._extractor = ChannelExtractor(
            input_channels=self._native_channels,
            output_channels=self._channels,
        )

        try:

            self._pcm = alsaaudio.PCM(

                type=alsaaudio.PCM_CAPTURE,

                mode=alsaaudio.PCM_NORMAL,

                device=device.id,

            )

            actual_rate = self._pcm.setrate(
                self._rate
            )

            if actual_rate and actual_rate != self._rate:
                self.logger.warning(
                    "ALSA hat eine andere Samplerate akzeptiert als "
                    "angefordert: gefordert %d Hz, gemeldet %d Hz.",
                    self._rate,
                    actual_rate,
                )

            self._pcm.setchannels(
                self._native_channels
            )

            self._pcm.setformat(
                self._format
            )

            self._pcm.setperiodsize(
                self._period_size
            )

            self.logger.info(
                "ALSA geöffnet: %s | Hardware: %d Ch | Aufnahme: %d Ch | %d Hz",
                device.id,
                self._native_channels,
                self._channels,
                self._rate,
            )

            return True

        except Exception as exc:

            self.logger.exception(
                "ALSA konnte nicht geöffnet werden: %s",
                exc,
            )

            self._pcm = None

            return False

    def restart_rate_measurement(self) -> None:
        """
        Startet ein neues Messfenster für die Ist-Samplerate, ohne
        das Gerät neu zu öffnen (siehe
        Application.check_sample_rate(), z.B. über den
        "Aktualisieren"-Knopf ausgelöst). Ohne das würde ein noch
        unfertiges Messfenster von einer früheren, länger
        zurückliegenden Prüfung mit der aktuellen Zeit vermischt und
        kurzzeitig einen völlig falschen Messwert liefern (Frames aus
        Sekunden vor einer Pause, geteilt durch die inzwischen
        vergangene reale Zeit).
        """

        if self._pcm is None:
            return

        self._rate_monitor.reset(self._rate)

    def close(self) -> None:
        """
        Schließt das Audiogerät.
        """

        if self._pcm is not None:

            self._pcm.close()

            self._pcm = None

        self._rate_monitor.reset(0)

        self.device = None

        self.logger.info(
            "ALSA-Gerät geschlossen."
        )

    # ---------------------------------------------------------
    # Lesen
    # ---------------------------------------------------------

    def read(self) -> bytes | None:
        """
        Liest einen Audiobuffer.
        """

        if self._pcm is None:
            return None

        length, data = self._pcm.read()

        if length <= 0:
            return None

        self._rate_monitor.record(length)

        return self._extractor.extract(data)

    # ---------------------------------------------------------
    # Diagnose
    # ---------------------------------------------------------

    def diagnose(self) -> list[DiagnosticItem]:
        """
        Führt eine Diagnose des Audio-Backends durch.
        """

        diagnostics: list[DiagnosticItem] = []

        diagnostics.append(
            DiagnosticItem(
                name="ALSA Device",
                ok=self.device is not None,
                message=(
                    self.device.id
                    if self.device is not None
                    else "Kein Gerät ausgewählt."
                ),
            )
        )

        diagnostics.append(
            DiagnosticItem(
                name="PCM Handle",
                ok=self.opened,
                message=(
                    "PCM erfolgreich geöffnet."
                    if self.opened
                    else "PCM nicht geöffnet."
                ),
            )
        )

        diagnostics.append(
            DiagnosticItem(
                name="Backend",
                ok=self.opened,
                message=(
                    "Backend bereit."
                    if self.opened
                    else "Backend geschlossen."
                ),
            )
        )

        return diagnostics
