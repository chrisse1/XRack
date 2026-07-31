"""
XRack Musikspieler.
"""

import logging
import threading
from pathlib import Path

import alsaaudio

from audio.audio_playback_backend import AudioPlaybackBackend
from audio.models import AudioDevice
from player.music_library import MusicLibrary
from player.track_decoder import TrackDecoder

CHANNELS = 2
CHUNK_FRAMES = 1024


class MusicPlayer:
    """
    Spielt Musikdateien auf frei wählbaren Kanälen ab - entweder
    einzeln oder als zufällig gemischte Endlosschleife über einen
    Ordner.
    """

    def __init__(
        self,
        backend: AudioPlaybackBackend,
        library: MusicLibrary,
    ):

        self.logger = logging.getLogger("XRack")

        self.backend = backend

        self.library = library

        self.decoder = TrackDecoder()

        self._playing = False

        self._thread: threading.Thread | None = None

        self._folder_mode = False

        self._playlist: list[Path] = []

        self._index = 0

        self._current_track = ""

        self._skip_requested = False

        self._channels = CHANNELS
        self._start_channel = 0
        self._rate = 48000

    @property
    def playing(self) -> bool:
        return self._playing

    @property
    def folder_mode(self) -> bool:
        return self._folder_mode

    @property
    def current_track(self) -> str:
        return self._current_track

    @property
    def channels(self) -> int:
        return self._channels

    @property
    def start_channel(self) -> int:
        return self._start_channel

    def play_folder(
        self,
        device: AudioDevice,
        folder: Path,
        start_channel: int,
    ) -> bool:
        """
        Spielt alle Musikdateien eines Ordners in zufälliger
        Reihenfolge in Dauerschleife ab.
        """

        if self.playing:
            return False

        playlist = self.library.build_shuffled_playlist(folder)

        if not playlist:
            return False

        return self._start(
            device,
            playlist,
            folder_mode=True,
            start_channel=start_channel,
        )

    def play_file(
        self,
        device: AudioDevice,
        path: Path,
        start_channel: int,
    ) -> bool:
        """
        Spielt eine einzelne Datei einmalig ab.
        """

        if self.playing:
            return False

        if not path.exists():
            return False

        return self._start(
            device,
            [path],
            folder_mode=False,
            start_channel=start_channel,
        )

    def stop(self) -> None:
        """
        Stoppt die Wiedergabe.
        """

        if not self.playing:
            return

        self._playing = False

        self.decoder.close()

        if self._thread is not None:

            self._thread.join()

            self._thread = None

    def skip(self) -> None:
        """
        Springt zum nächsten Titel (nur im Ordner-Modus sinnvoll).
        """

        if not self.playing:
            return

        self._skip_requested = True

        self.decoder.close()

    def _start(
        self,
        device: AudioDevice,
        playlist: list[Path],
        folder_mode: bool,
        start_channel: int,
    ) -> bool:

        self._playlist = playlist
        self._index = 0
        self._folder_mode = folder_mode
        self._channels = CHANNELS
        self._start_channel = start_channel

        if not self.backend.open(
            device,
            channels=self._channels,
            rate=self._rate,
            start_channel=self._start_channel,
            sample_format=alsaaudio.PCM_FORMAT_S32_LE,
        ):
            return False

        self._playing = True

        self._thread = threading.Thread(
            target=self._worker,
            daemon=True,
        )

        self._thread.start()

        self.logger.info(
            "Musikspieler gestartet: %s (%d Titel, Modus=%s)",
            playlist[0].name,
            len(playlist),
            "Ordner" if folder_mode else "Einzeltitel",
        )

        return True

    def _worker(self) -> None:

        chunk_bytes = (
            CHUNK_FRAMES *
            self._channels *
            AudioPlaybackBackend.BYTES_PER_SAMPLE
        )

        consecutive_failures = 0

        while self._playing:

            if self._index >= len(self._playlist):

                if self._folder_mode:
                    self._playlist = self.library.build_shuffled_playlist(
                        self._playlist[0].parent
                    )
                    self._index = 0

                    if not self._playlist:
                        break
                else:
                    break

            track = self._playlist[self._index]

            self._current_track = track.name

            self._skip_requested = False

            if not self.decoder.open(
                track,
                channels=self._channels,
                rate=self._rate,
            ):
                self._index += 1
                consecutive_failures += 1

                if consecutive_failures >= 3:
                    self.logger.error(
                        "Musikspieler: zu viele Dateien konnten nicht "
                        "dekodiert werden, Wiedergabe wird gestoppt."
                    )
                    break

                continue

            consecutive_failures = 0

            while self._playing and not self._skip_requested:

                data = self.decoder.read(chunk_bytes)

                if data is None:
                    break

                self.backend.write(data)

            self.decoder.close()

            self._index += 1

        self._playing = False

        self._current_track = ""

        self.backend.close()

        self.logger.info(
            "Musikspieler gestoppt."
        )
