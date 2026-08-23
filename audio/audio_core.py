"""
Audio Core

Diese Klasse verwaltet später den exklusiven Zugriff auf das Audio-Interface.
Im ersten Schritt ist sie nur ein Platzhalter.
"""
from audio.audio_backend import AudioBackend
from audio.models import (
    AudioDevice,
    AudioState,
    AudioHealth,
    DiagnosticItem,
)
import logging

class AudioCore:
    """Audio Core."""

    def __init__(self):

        self.device: AudioDevice | None = None
        
        self.state = AudioState.CLOSED
        
        self.health = AudioHealth.NOT_READY

        self.logger = logging.getLogger("XRack")
        
        self.backend = AudioBackend()

    @property
    def opened(self) -> bool:
        """True, wenn der Audio Core geöffnet ist."""

        return self.state != AudioState.CLOSED
        
    @property
    def alsa_name(self) -> str:
        """
        Liefert den ALSA-Gerätenamen.
        """

        return self.backend.alsa_name
            
    @property
    def name(self) -> str:
        """Name des Audiogeräts."""

        if self.device is None:
            return ""

        return self.device.name


    @property
    def max_channels(self) -> int:
        """Maximale Kanalzahl."""

        if self.device is None:
            return 0

        return self.device.channels


    @property
    def sample_rate(self) -> int:
        """
        Tatsächlich beim Öffnen verwendete Abtastrate (vom Nutzer
        erklärt, siehe Application.set_mixer_sample_rate()) - nicht
        der von ALSA gemeldete Wertebereich (device.sample_rate).
        """

        if self.device is None:
            return 0

        return self.backend.rate

    @property
    def sample_bits(self) -> int:
        """Bitauflösung."""

        if self.device is None:
            return 0

        return self.device.sample_bits


    @property
    def formats(self) -> list[str]:
        """Unterstützte Audioformate."""

        if self.device is None:
            return []

        return self.device.formats
        
    def open(
        self,
        device: AudioDevice,
        channels: int | None = None,
        rate: int | None = None,
    ) -> bool:

        if not self.backend.open(
            device,
            channels,
            rate,
        ):
            return False

        self.device = device

        self.logger.info(
            "Audio Core geöffnet: %s | %s | %d Kanäle | %d Hz",
            self.name,
            self.alsa_name,
            self.max_channels,
            self.sample_rate,
        )
        
        self.state = AudioState.OPEN
        
        self.health = AudioHealth.READY
        
        for item in self.diagnose():
            self.logger.info(
                "[Diagnose] %s: %s",
                item.name,
                item.message,
            )

        return True

    def close(self) -> None:
        """
        Schließt den Audio Core.
        """
        self.backend.close()

        self.device = None

        self.logger.info("Audio Core geschlossen.")

        self.state = AudioState.CLOSED
        
        self.health = AudioHealth.NOT_READY
        
    @property
    def ready(self) -> bool:
        """
        True, wenn der Audio Core betriebsbereit ist.
        """

        return self.health == AudioHealth.READY
        
    def diagnose(self) -> list[DiagnosticItem]:
        """
        Führt eine Diagnose des Audio Cores durch.
        """

        diagnostics = []

        diagnostics.append(
            DiagnosticItem(
                name="AudioDevice",
                ok=self.device is not None,
                message=(
                    "Audiogerät übernommen."
                    if self.device is not None
                    else "Kein Audiogerät vorhanden."
                ),
            )
        )

        diagnostics.extend(
            self.backend.diagnose()
        )

        return diagnostics
