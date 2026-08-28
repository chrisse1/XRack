"""
XRack Musikspieler.
"""

import logging
import threading
from pathlib import Path
from time import monotonic

import alsaaudio

from audio.audio_playback_backend import AudioPlaybackBackend
from audio.models import AudioDevice
from player.music_library import MusicLibrary
from player.track_decoder import TrackDecoder, probe_duration, probe_tags

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

        self._paused = False

        self._pause_event = threading.Event()
        self._pause_event.set()

        self._resume_position = 0.0

        self._thread: threading.Thread | None = None

        self._folder_mode = False

        self._playlist: list[Path] = []

        self._index = 0

        self._current_track = ""
        self._current_track_title = ""
        self._current_track_artist = ""

        self._skip_requested = False

        self._seek_target: float | None = None

        self._track_duration = 0.0
        self._track_offset = 0.0
        self._track_start_time = monotonic()

        self._channels = CHANNELS
        self._start_channel = 0
        self._rate = 0

    @property
    def playing(self) -> bool:
        return self._playing

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def folder_mode(self) -> bool:
        return self._folder_mode

    @property
    def current_track(self) -> str:
        return self._current_track

    @property
    def current_track_title(self) -> str:
        return self._current_track_title

    @property
    def current_track_artist(self) -> str:
        return self._current_track_artist

    @property
    def channels(self) -> int:
        return self._channels

    @property
    def start_channel(self) -> int:
        return self._start_channel

    @property
    def track_duration(self) -> float:
        return self._track_duration

    @property
    def track_position(self) -> float:
        """
        Verstrichene Zeit im aktuellen Titel (Sekunden).
        """

        if not self.playing:
            return 0.0

        if self.paused:
            return self._resume_position

        return (
            self._track_offset +
            (monotonic() - self._track_start_time)
        )

    def play_folder(
        self,
        device: AudioDevice,
        folder: Path,
        start_channel: int,
        rate: int,
    ) -> bool:
        """
        Spielt alle Musikdateien eines Ordners in zufälliger
        Reihenfolge in Dauerschleife ab. Löst eine bereits laufende
        Musikwiedergabe ab (Titel-/Ordnerwechsel).
        """

        if self.playing:
            self.stop()

        playlist = self.library.build_shuffled_playlist(folder)

        if not playlist:
            return False

        return self._start(
            device,
            playlist,
            folder_mode=True,
            start_channel=start_channel,
            rate=rate,
        )

    def play_file(
        self,
        device: AudioDevice,
        path: Path,
        start_channel: int,
        rate: int,
    ) -> bool:
        """
        Spielt eine einzelne Datei einmalig ab. Löst eine bereits
        laufende Musikwiedergabe ab (Titel-/Ordnerwechsel).
        """

        if self.playing:
            self.stop()

        if not path.exists():
            return False

        return self._start(
            device,
            [path],
            folder_mode=False,
            start_channel=start_channel,
            rate=rate,
        )

    #
    # Wie lange stop() hoechstens auf das Ende des Worker-Threads
    # wartet, und wie lange ein neuer Start auf einen alten Thread
    # wartet.
    #
    # Warum ueberhaupt eine Grenze: Der Worker liest vor jedem Titel
    # die Metadaten (probe_tags/probe_duration in
    # player/track_decoder.py) - zwei ffprobe-Aufrufe mit je zehn
    # Sekunden eigener Zeitgrenze. Steckt er gerade darin, kann er
    # nicht sofort anhalten. Frueher wartete stop() unbegrenzt mit;
    # der Stop-Knopf wirkte dann bis zu zwanzig Sekunden tot.
    #
    # Das Warten ist beim Stoppen falsch und beim Starten richtig:
    # Anhalten soll sofort wirken, und dass der Thread ein paar
    # Sekunden spaeter zu Ende laeuft, stoert niemanden - _playing
    # steht ja bereits auf False, er schreibt nichts mehr ans
    # Audiogeraet. Einen neuen Titel zu beginnen muss dagegen warten,
    # sonst liefen zwei Worker auf demselben Geraet.
    #
    # Eine halbe Sekunde reicht dem Normalfall reichlich: Steckt der
    # Worker in der Leseschleife, endet er in Millisekunden. Laenger
    # zu warten hilft nur dem Fall, den wir gerade nicht mehr abwarten
    # wollen.
    STOP_JOIN_TIMEOUT = 0.5
    START_JOIN_TIMEOUT = 25.0

    def stop(self) -> None:
        """
        Stoppt die Wiedergabe.

        Kehrt zurueck, sobald feststeht, dass nichts mehr abgespielt
        wird - nicht erst, wenn der Worker-Thread auch wirklich zu
        Ende ist (siehe STOP_JOIN_TIMEOUT).
        """

        if not self.playing:
            return

        self._playing = False

        #
        # Eine pausierte Wiedergabe wartet im Worker-Thread auf
        # das Event - ohne das Aufwecken hier würde stop() dort
        # ewig hängen bleiben (join() wartet auf den Thread).
        #
        self._paused = False
        self._pause_event.set()

        self.decoder.close()

        if self._thread is None:
            return

        self._thread.join(timeout=self.STOP_JOIN_TIMEOUT)

        if self._thread.is_alive():

            #
            # Der Thread haengt noch in einer Metadaten-Abfrage. Er
            # endet von selbst, sobald sie zurueckkommt. Die Referenz
            # bleibt stehen, damit ein neuer Start ihn abwarten kann.
            #
            self.logger.info(
                "Musikspieler: Wiedergabe beendet, der Lese-Thread "
                "laeuft noch kurz nach (vermutlich eine "
                "Metadaten-Abfrage)."
            )

            return

        self._thread = None

    def _warte_auf_alten_thread(self) -> bool:
        """
        Wartet, bis ein noch laufender Worker-Thread zu Ende ist.

        Wird vor jedem Start gebraucht: Zwei Worker auf demselben
        Audiogeraet wuerden sich gegenseitig die Ausgabe zerschneiden.
        Liefert False, wenn der alte Thread nicht rechtzeitig endet -
        dann wird nicht gestartet, statt das Risiko einzugehen.
        """

        if self._thread is None or not self._thread.is_alive():
            self._thread = None
            return True

        self._thread.join(timeout=self.START_JOIN_TIMEOUT)

        if self._thread.is_alive():

            self.logger.error(
                "Musikspieler: Der vorherige Lese-Thread laeuft nach "
                "%.0f s immer noch - es wird nichts Neues gestartet.",
                self.START_JOIN_TIMEOUT,
            )

            return False

        self._thread = None

        return True

    def pause(self) -> None:
        """
        Pausiert die Wiedergabe. Das Audiogerät bleibt geöffnet
        (reserviert), damit sofort fortgesetzt werden kann - ein
        gleichzeitiger Soundcheck ist währenddessen nicht möglich.
        """

        if not self.playing or self.paused:
            return

        self._resume_position = self.track_position

        self._paused = True

        self._pause_event.clear()

        self.decoder.close()

    def resume(self) -> None:
        """
        Setzt eine pausierte Wiedergabe fort.
        """

        if not self.playing or not self.paused:
            return

        self._paused = False

        self._pause_event.set()

    def skip(self) -> None:
        """
        Springt zum nächsten Titel (nur im Ordner-Modus sinnvoll).
        """

        if not self.playing:
            return

        self._skip_requested = True

        self._wake_if_paused()

        self.decoder.close()

    def seek(self, position: float) -> None:
        """
        Springt an eine Position (Sekunden) im aktuellen Titel.
        """

        if not self.playing:
            return

        self._seek_target = max(0.0, position)

        self._wake_if_paused()

        self.decoder.close()

    def _wake_if_paused(self) -> None:
        """
        Weckt eine pausierte Wiedergabe auf (z.B. für Spulen/Weiter,
        während pausiert ist).
        """

        if self._paused:
            self._paused = False
            self._pause_event.set()

    def _start(
        self,
        device: AudioDevice,
        playlist: list[Path],
        folder_mode: bool,
        start_channel: int,
        rate: int,
    ) -> bool:

        self._playlist = playlist
        self._index = 0
        self._folder_mode = folder_mode
        self._channels = CHANNELS
        self._start_channel = start_channel
        self._rate = rate

        self._paused = False
        self._pause_event.set()

        if not self.backend.open(
            device,
            channels=self._channels,
            rate=self._rate,
            start_channel=self._start_channel,
            sample_format=alsaaudio.PCM_FORMAT_S32_LE,
        ):
            return False

        #
        # Erst sicherstellen, dass kein alter Worker mehr laeuft -
        # stop() wartet darauf bewusst nicht mehr (siehe dort).
        #
        if not self._warte_auf_alten_thread():
            self.backend.close()
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

            #
            # Zwischen der Pruefung oben und hier kann stop() gelaufen
            # sein. Dann diesen Titel gar nicht erst einlesen - die
            # beiden ffprobe-Aufrufe kosten sonst bis zu zwanzig
            # Sekunden fuer nichts, und genau die haengen den Thread
            # ueber das Ende der Wiedergabe hinaus.
            #
            if not self._playing:
                break

            tags = probe_tags(track)
            self._current_track_title = tags["title"]
            self._current_track_artist = tags["artist"]

            self._track_duration = probe_duration(track)

            if self._play_track(track, chunk_bytes):
                consecutive_failures = 0
            else:
                consecutive_failures += 1

                if consecutive_failures >= 3:
                    self.logger.error(
                        "Musikspieler: zu viele Dateien konnten nicht "
                        "dekodiert werden, Wiedergabe wird gestoppt."
                    )
                    break

            self._index += 1

        self._playing = False

        self._current_track = ""
        self._current_track_title = ""
        self._current_track_artist = ""

        self.backend.close()

        self.logger.info(
            "Musikspieler gestoppt."
        )

    def _play_track(self, track: Path, chunk_bytes: int) -> bool:
        """
        Spielt einen einzelnen Titel ab und dekodiert ihn bei Bedarf
        (Spulen) erneut ab einer neuen Position. Liefert False, wenn
        die Datei nicht geöffnet werden konnte.
        """

        position = 0.0

        opened_at_least_once = False

        while self._playing:

            self._skip_requested = False
            self._seek_target = None

            self._track_offset = position
            self._track_start_time = monotonic()

            if not self.decoder.open(
                track,
                channels=self._channels,
                rate=self._rate,
                start_position=position,
            ):
                return opened_at_least_once

            opened_at_least_once = True

            while (
                self._playing
                and not self._skip_requested
                and self._seek_target is None
                and not self._paused
            ):

                data = self.decoder.read(chunk_bytes)

                if data is None:
                    break

                self.backend.write(data)

            #
            # Den Pausen-Zustand merken, BEVOR geschlossen wird.
            #
            # close() beendet ffmpeg und wartet bis zu zwei Sekunden
            # auf dessen Ende (player/track_decoder.py). Wuerde unten
            # erneut self._paused gelesen, koennte in dieser Zeit
            # "Fortsetzen" eingetroffen sein - dann stuende dort
            # schon wieder False, die Pausen-Behandlung fiele aus,
            # und _play_track liefe auf das break am Ende: naechster
            # Titel statt Weiterspielen. Genau das ist im Betrieb
            # passiert, je nachdem wie schnell jemand nach Pause auf
            # Fortsetzen geklickt hat.
            #
            # Kam das Fortsetzen waehrend des Schliessens, ist
            # _pause_event bereits gesetzt - wait() kehrt sofort
            # zurueck, und es geht an der gemerkten Stelle weiter.
            #
            war_pausiert = self._paused

            self.decoder.close()

            if self._playing and war_pausiert:

                self._pause_event.wait()

                if not self._playing:
                    break

                if self._skip_requested:
                    break

                position = (
                    self._seek_target
                    if self._seek_target is not None
                    else self._resume_position
                )
                continue

            if self._playing and self._seek_target is not None:
                position = self._seek_target
                continue

            break

        return opened_at_least_once
