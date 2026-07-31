"""
Low-Level Zugriff auf das Audio-Interface für die Wiedergabe.
"""

import logging

import alsaaudio

from audio.channel_inserter import ChannelInserter
from audio.models import AudioDevice


class AudioPlaybackBackend:
    """Kommuniziert direkt mit ALSA (Wiedergabe)."""

    BYTES_PER_SAMPLE = 4

    def __init__(self):

        self.logger = logging.getLogger("XRack")

        self.device: AudioDevice | None = None

        self._pcm = None

        self._rate = 0
        self._channels = 0
        self._native_channels = 0
        self._format = None
        self._inserter: ChannelInserter | None = None

    @property
    def opened(self) -> bool:
        """True, wenn ein PCM-Handle geöffnet ist."""
        return self._pcm is not None

    def open(
        self,
        device: AudioDevice,
        channels: int,
        rate: int,
    ) -> bool:
        """
        Öffnet das Audiogerät für die Wiedergabe.

        Genau wie beim Aufnehmen wird auch hier immer mit der
        vollen, nativen Kanalzahl des Interfaces geöffnet. Die
        Datei bringt ggf. weniger Kanäle mit (z.B. 8 statt 18) -
        diese werden per ChannelInserter auf die ersten Kanäle des
        Interfaces gelegt, alle übrigen Kanäle bleiben stumm. So
        landet das Signal wieder auf genau den Kanälen, auf denen
        es aufgenommen wurde.
        """

        self.device = device

        self._rate = rate
        self._native_channels = device.channels
        self._channels = channels
        self._format = alsaaudio.PCM_FORMAT_S24_LE

        self._inserter = ChannelInserter(
            input_channels=self._channels,
            output_channels=self._native_channels,
        )

        try:

            self._pcm = alsaaudio.PCM(

                type=alsaaudio.PCM_PLAYBACK,

                mode=alsaaudio.PCM_NORMAL,

                device=device.id,

            )

            self._pcm.setrate(
                self._rate
            )

            self._pcm.setchannels(
                self._native_channels
            )

            self._pcm.setformat(
                self._format
            )

            self._pcm.setperiodsize(1024)

            self.logger.info(
                "ALSA Wiedergabe geöffnet: %s | Hardware: %d Ch | Datei: %d Ch | %d Hz",
                device.id,
                self._native_channels,
                self._channels,
                self._rate,
            )

            return True

        except Exception as exc:

            self.logger.exception(
                "ALSA Wiedergabe konnte nicht geöffnet werden: %s",
                exc,
            )

            self._pcm = None

            return False

    def write(self, data: bytes) -> None:
        """
        Schreibt einen Puffer an das Wiedergabegerät.
        """

        if self._pcm is None:
            return

        self._pcm.write(
            self._inserter.insert(data)
        )

    def close(self) -> None:
        """
        Schließt das Wiedergabegerät.
        """

        if self._pcm is not None:

            self._pcm.close()

            self._pcm = None

        self.device = None

        self.logger.info(
            "ALSA-Wiedergabegerät geschlossen."
        )
