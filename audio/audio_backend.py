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

        self._capture = True

    @property
    def opened(self) -> bool:
        """
        True, wenn ein PCM-Handle geöffnet ist.
        """

        return self._pcm is not None

    @property
    def alsa_name(self) -> str:
        """
        Liefert den ALSA-Gerätenamen.
        """

        if self.device is None:
            return ""

        return f"hw:{self.device.card},{self.device.device}"

    def open(self, device: AudioDevice) -> bool:
        """
        Öffnet das Audiogerät exklusiv.
        """

        self.device = device

        try:

            self._pcm = alsaaudio.PCM(
                type=alsaaudio.PCM_CAPTURE,
                mode=alsaaudio.PCM_NORMAL,
                device=device.id,
            )

            self.logger.info(
                "ALSA-Gerät geöffnet: %s",
                device.id,
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
