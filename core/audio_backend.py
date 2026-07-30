"""
Low-Level Zugriff auf das Audio-Interface.

Diese Klasse kapselt den direkten Zugriff auf ALSA.
"""

import logging

import alsaaudio

from audio.models import AudioDevice, DiagnosticItem


class AudioBackend:
    """Kommuniziert direkt mit ALSA."""

    def __init__(self):

        self.logger = logging.getLogger("XRack")

        self.device: AudioDevice | None = None

        self._pcm = None

        self._rate = 0
        self._channels = 0
        self._period_size = 0
        self._format = None

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
    ) -> bool:
        """
        Öffnet das Audiogerät.
        """

        self.device = device

        self._rate = device.sample_rate
        self._channels = (
            channels
            if channels is not None
            else device.channels
        )
        self._period_size = 1024

        self._format = alsaaudio.PCM_FORMAT_S24_LE

        try:

            self._pcm = alsaaudio.PCM(

                type=alsaaudio.PCM_CAPTURE,

                mode=alsaaudio.PCM_NORMAL,

                device=device.id,

            )

            self._pcm.setrate(
                self._rate
            )

            self._pcm.setchannels(
                self._channels
            )

            self._pcm.setformat(
                self._format
            )

            self._pcm.setperiodsize(
                self._period_size
            )

            self.logger.info(
                "ALSA geöffnet: %s | %d Ch | %d Hz",
                device.id,
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

    def close(self) -> None:
        """
        Schließt das Audiogerät.
        """

        if self._pcm is not None:

            self._pcm.close()

            self._pcm = None

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

        return data

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
