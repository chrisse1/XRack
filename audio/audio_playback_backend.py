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
        start_channel: int = 0,
        sample_format: int = alsaaudio.PCM_FORMAT_S24_LE,
    ) -> bool:
        """
        Öffnet das Audiogerät für die Wiedergabe.

        Genau wie beim Aufnehmen wird auch hier immer mit der
        vollen, nativen Kanalzahl des Interfaces geöffnet. Die
        Quelle bringt ggf. weniger Kanäle mit (z.B. 2 für Stereo-
        Musik) - diese werden per ChannelInserter ab `start_channel`
        auf die Kanäle des Interfaces gelegt, alle übrigen Kanäle
        bleiben stumm. So landet z.B. eine Aufnahme wieder auf
        genau den Kanälen, auf denen sie aufgenommen wurde
        (start_channel=0), oder Musik auf frei wählbaren Kanälen
        (z.B. start_channel=16 für Kanal 17+18).

        `sample_format` ist wählbar (aber immer 4 Byte pro Sample,
        siehe BYTES_PER_SAMPLE), da Musikdateien über ffmpeg als
        volles S32_LE dekodiert werden, während Aufnahmen im
        S24_LE-Format (24 Bit in einem 32-Bit-Container) vorliegen.
        """

        self.device = device

        self._rate = rate
        self._native_channels = device.channels
        self._channels = channels
        self._format = sample_format

        self._inserter = ChannelInserter(
            input_channels=self._channels,
            output_channels=self._native_channels,
            start_channel=start_channel,
        )

        try:

            self._pcm = alsaaudio.PCM(

                type=alsaaudio.PCM_PLAYBACK,

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

            actual_format = self._pcm.setformat(
                self._format
            )

            if actual_format is not None and actual_format != self._format:
                self.logger.warning(
                    "ALSA hat ein anderes Sampleformat akzeptiert als "
                    "angefordert: gefordert %s, gemeldet %s.",
                    self._format,
                    actual_format,
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
